"""Recurring Failure Detection Service Layer."""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.entities.test_case import TestCase
from app.models.schemas.recurring_failure import (
    AnalyzeHistoricalFailuresRequest,
    EndpointFailureRecurrence,
    HistoricalExecutionSample,
    PersistenceRating,
    ProjectRecurringFailureReport,
    TestCaseFailureRecurrence,
)
from app.utils.failure_fingerprinter import (
    calculate_persistence_rating,
    cluster_failure_samples,
)

logger = logging.getLogger("app.services.recurring_failure")


class RecurringFailureService:
    """Service providing historical failure aggregation and root-cause cluster analytics."""

    @classmethod
    def analyze_batch_samples(
        cls,
        req: AnalyzeHistoricalFailuresRequest
    ) -> ProjectRecurringFailureReport:
        """Analyze a collection of historical execution samples across arbitrary endpoints."""
        samples = req.samples
        total_runs = len(samples)

        # Group samples by endpoint_id
        samples_by_endpoint: Dict[int, List[HistoricalExecutionSample]] = {}
        for s in samples:
            eid = s.endpoint_id or 0
            if eid not in samples_by_endpoint:
                samples_by_endpoint[eid] = []
            samples_by_endpoint[eid].append(s)

        endpoint_recurrences: List[EndpointFailureRecurrence] = []

        for eid, ep_samples in samples_by_endpoint.items():
            # Sort by timestamp ascending
            sorted_ep_samples = sorted(ep_samples, key=lambda x: x.timestamp)
            recent_window = sorted_ep_samples[-req.window_size:]
            pass_flags = [s.passed for s in recent_window]

            rating, consec_fails, fail_rate, is_flapping = calculate_persistence_rating(pass_flags)

            last_ts = sorted_ep_samples[-1].timestamp if sorted_ep_samples else None
            failed_count = sum(1 for s in recent_window if not s.passed)
            passed_count = len(recent_window) - failed_count

            endpoint_recurrences.append(
                EndpointFailureRecurrence(
                    endpoint_id=eid,
                    endpoint_name=f"Endpoint #{eid}",
                    http_method="ANY",
                    path=f"/api/resource/{eid}",
                    total_recorded_runs=len(recent_window),
                    failed_runs=failed_count,
                    passed_runs=passed_count,
                    failure_rate_pct=fail_rate,
                    consecutive_failures=consec_fails,
                    persistence_rating=rating,
                    is_flapping=is_flapping,
                    last_executed_at=last_ts,
                    recent_history=pass_flags
                )
            )

        # Sort top recurring failures: CHRONIC first, then INTERMITTENT, NEW, RESOLVED, HEALTHY
        severity_order = {
            PersistenceRating.CHRONIC: 0,
            PersistenceRating.INTERMITTENT: 1,
            PersistenceRating.NEW: 2,
            PersistenceRating.RESOLVED: 3,
            PersistenceRating.HEALTHY: 4
        }
        sorted_recurrences = sorted(
            endpoint_recurrences,
            key=lambda x: (severity_order.get(x.persistence_rating, 5), -x.failure_rate_pct, -x.consecutive_failures)
        )

        # Failure clusters
        clusters = cluster_failure_samples(samples)

        chronic_c = sum(1 for r in endpoint_recurrences if r.persistence_rating == PersistenceRating.CHRONIC)
        interm_c = sum(1 for r in endpoint_recurrences if r.persistence_rating == PersistenceRating.INTERMITTENT)
        new_c = sum(1 for r in endpoint_recurrences if r.persistence_rating == PersistenceRating.NEW)
        healthy_c = sum(1 for r in endpoint_recurrences if r.persistence_rating in (PersistenceRating.HEALTHY, PersistenceRating.RESOLVED))

        return ProjectRecurringFailureReport(
            project_id=None,
            project_name=req.project_name,
            total_analyzed_runs=total_runs,
            total_endpoints=len(endpoint_recurrences),
            chronic_failure_count=chronic_c,
            intermittent_failure_count=interm_c,
            new_failure_count=new_c,
            healthy_count=healthy_c,
            top_recurring_failures=sorted_recurrences,
            failure_clusters=clusters
        )

    @classmethod
    def analyze_project_recurrence(
        cls,
        project_id: int,
        db: Session,
        window_size: int = 10,
        historical_samples: Optional[List[HistoricalExecutionSample]] = None
    ) -> ProjectRecurringFailureReport:
        """Analyze project endpoints and cluster recurring failure patterns from database records or provided historical samples."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        endpoints = db.query(Endpoint).filter(Endpoint.project_id == project_id).all()
        samples = historical_samples or []

        # If no explicit telemetry samples provided, evaluate registered endpoints and test cases
        if not samples:
            for ep in endpoints:
                if ep.test_cases:
                    for tc in ep.test_cases:
                        # Synthetic baseline for active test cases
                        samples.append(
                            HistoricalExecutionSample(
                                endpoint_id=ep.id,
                                test_case_id=tc.id,
                                passed=tc.is_active,
                                status_code=200 if tc.is_active else 500,
                                error_message=None if tc.is_active else "Test case disabled / unverified",
                                timestamp=datetime.now(timezone.utc)
                            )
                        )
                else:
                    samples.append(
                        HistoricalExecutionSample(
                            endpoint_id=ep.id,
                            test_case_id=None,
                            passed=True,
                            status_code=200,
                            timestamp=datetime.now(timezone.utc)
                        )
                    )

        req = AnalyzeHistoricalFailuresRequest(
            samples=samples if samples else [
                HistoricalExecutionSample(
                    endpoint_id=endpoints[0].id if endpoints else 1,
                    passed=True,
                    status_code=200
                )
            ],
            project_name=project.name,
            window_size=window_size
        )

        report = cls.analyze_batch_samples(req)
        report.project_id = project.id
        report.project_name = project.name

        # Map actual endpoint details to recurrences
        ep_map = {ep.id: ep for ep in endpoints}
        for rec in report.top_recurring_failures:
            if rec.endpoint_id in ep_map:
                ep_obj = ep_map[rec.endpoint_id]
                rec.endpoint_name = ep_obj.name
                rec.http_method = ep_obj.method
                rec.path = ep_obj.path

        return report

    @classmethod
    def analyze_endpoint_recurrence(
        cls,
        endpoint_id: int,
        db: Session,
        samples: Optional[List[HistoricalExecutionSample]] = None,
        window_size: int = 10
    ) -> EndpointFailureRecurrence:
        """Analyze single endpoint failure history and persistence rating."""
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise ValueError(f"Endpoint #{endpoint_id} not found.")

        ep_samples = [s for s in (samples or []) if s.endpoint_id == endpoint_id]

        if not ep_samples:
            # Fallback when no telemetry exists
            return EndpointFailureRecurrence(
                endpoint_id=endpoint.id,
                endpoint_name=endpoint.name,
                http_method=endpoint.method,
                path=endpoint.path,
                total_recorded_runs=1,
                failed_runs=0,
                passed_runs=1,
                failure_rate_pct=0.0,
                consecutive_failures=0,
                persistence_rating=PersistenceRating.HEALTHY,
                is_flapping=False,
                last_executed_at=datetime.now(timezone.utc),
                recent_history=[True]
            )

        sorted_samples = sorted(ep_samples, key=lambda x: x.timestamp)[-window_size:]
        pass_flags = [s.passed for s in sorted_samples]
        rating, consec_fails, fail_rate, is_flapping = calculate_persistence_rating(pass_flags)

        failed_c = sum(1 for s in sorted_samples if not s.passed)
        passed_c = len(sorted_samples) - failed_c

        return EndpointFailureRecurrence(
            endpoint_id=endpoint.id,
            endpoint_name=endpoint.name,
            http_method=endpoint.method,
            path=endpoint.path,
            total_recorded_runs=len(sorted_samples),
            failed_runs=failed_c,
            passed_runs=passed_c,
            failure_rate_pct=fail_rate,
            consecutive_failures=consec_fails,
            persistence_rating=rating,
            is_flapping=is_flapping,
            last_executed_at=sorted_samples[-1].timestamp,
            recent_history=pass_flags
        )