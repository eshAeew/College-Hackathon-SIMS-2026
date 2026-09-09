"""Inconsistent Behavior Service: Multi-Execution Repetitive Runner and Flakiness Analyzer."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities.endpoint import Endpoint
from app.models.schemas.inconsistent_behavior import (
    ExecutionMode,
    FlakinessVerdict,
    ExecutionIterationResult,
    LatencyStatistics,
    StatusCodeAnalysis,
    PayloadConsistencyAnalysis,
    FlakinessReport,
    MultiExecutionRequest,
    EndpointMultiExecutionRequest,
    AnalyzeBatchRequest,
)
from app.models.schemas.execution import (
    EndpointExecutionRequest,
    ExecutionOptions,
    ExecutionResultResponse,
)
from app.services.http_dispatcher import HttpDispatcherService
from app.utils.statistics_calculator import (
    compute_latency_stats,
    compute_status_entropy,
    compute_payload_hashes,
    evaluate_flakiness,
)

logger = logging.getLogger("app.services.inconsistency_service")


class InconsistencyService:
    """Service layer managing repetitive test execution, status entropy, latency variance, and flakiness detection."""

    @classmethod
    def _compute_body_hash(cls, body: Any) -> str:
        """Compute 12-char SHA-256 hash for body payload."""
        if body is None:
            raw_str = "__EMPTY__"
        elif isinstance(body, (dict, list)):
            try:
                raw_str = json.dumps(body, sort_keys=True)
            except Exception:
                raw_str = str(body)
        else:
            raw_str = str(body)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def _build_report_from_iterations(
        cls,
        target_name: str,
        execution_mode: str,
        iterations: List[ExecutionIterationResult],
        raw_bodies: List[Any]
    ) -> FlakinessReport:
        """Calculate statistical metrics and build FlakinessReport from iteration results."""
        total_runs = len(iterations)
        successful_runs = sum(1 for it in iterations if it.is_success)
        failed_runs = total_runs - successful_runs
        pass_rate = round((successful_runs / total_runs) * 100, 2) if total_runs > 0 else 0.0
        fail_rate = round((failed_runs / total_runs) * 100, 2) if total_runs > 0 else 0.0

        latencies = [it.elapsed_ms for it in iterations]
        status_codes = [it.status_code for it in iterations]

        # 1. Latency Distribution
        lat_dict = compute_latency_stats(latencies)
        latency_stats = LatencyStatistics(**lat_dict)

        # 2. Status Entropy & Transitions
        status_dict = compute_status_entropy(status_codes)
        status_analysis = StatusCodeAnalysis(**status_dict)

        # 3. Payload Body Consistency
        payload_dict = compute_payload_hashes(raw_bodies)
        payload_analysis = PayloadConsistencyAnalysis(**payload_dict)

        # 4. Flakiness Scoring & Verdict
        flakiness_score, verdict_str, findings, recommendations = evaluate_flakiness(
            total_runs=total_runs,
            status_analysis=status_dict,
            latency_stats=lat_dict,
            payload_analysis=payload_dict
        )

        is_flaky = (flakiness_score > 0.0)

        # Summary statement
        status_str = "consistent" if status_analysis.is_status_consistent else "flaky/varying"
        summary = (
            f"Multi-Run Analysis for {target_name} ({total_runs} runs): "
            f"Pass Rate: {pass_rate}%, Status Behavior: {status_str}, "
            f"Mean Latency: {latency_stats.mean_latency_ms}ms (Jitter: {latency_stats.jitter_ms}ms), "
            f"Flakiness Score: {flakiness_score}% [{verdict_str}]."
        )

        return FlakinessReport(
            target=target_name,
            total_runs=total_runs,
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            pass_rate_percent=pass_rate,
            failure_rate_percent=fail_rate,
            execution_mode=execution_mode,
            status_analysis=status_analysis,
            latency_statistics=latency_stats,
            payload_analysis=payload_analysis,
            flakiness_score=flakiness_score,
            is_flaky=is_flaky,
            verdict=FlakinessVerdict(verdict_str),
            findings=findings,
            recommendations=recommendations,
            iterations=iterations,
            summary=summary
        )

    @classmethod
    async def run_direct_multi_execution(
        cls,
        req: MultiExecutionRequest
    ) -> FlakinessReport:
        """Run repetitive multi-execution on an ad-hoc direct HTTP request."""
        target_name = f"[{req.direct_request.method.value}] {req.direct_request.base_url}{req.direct_request.path}"
        iterations: List[ExecutionIterationResult] = []
        raw_bodies: List[Any] = []

        async def _execute_single(idx: int) -> Tuple[ExecutionIterationResult, Any]:
            ts = datetime.now(timezone.utc).isoformat()
            try:
                res: ExecutionResultResponse = await HttpDispatcherService.dispatch_direct(req.direct_request)
                status_code = res.status_code
                status_text = res.status_text
                elapsed = res.elapsed_ms
                body = res.body
                error = res.error
                is_success = res.is_success
            except Exception as exc:
                status_code = None
                status_text = "Execution Error"
                elapsed = 0.0
                body = None
                error = str(exc)
                is_success = False

            payload_hash = cls._compute_body_hash(body)
            iter_result = ExecutionIterationResult(
                iteration=idx,
                timestamp=ts,
                status_code=status_code,
                status_text=status_text,
                elapsed_ms=round(elapsed, 3),
                payload_hash=payload_hash,
                is_success=is_success,
                error=error
            )
            return iter_result, body

        if req.mode == ExecutionMode.SEQUENTIAL:
            for i in range(1, req.iterations + 1):
                if i > 1 and req.delay_ms > 0:
                    await asyncio.sleep(req.delay_ms / 1000.0)
                it_res, body = await _execute_single(i)
                iterations.append(it_res)
                raw_bodies.append(body)
        else:
            # Concurrent execution with semaphore limit
            semaphore = asyncio.Semaphore(req.concurrency_limit)

            async def _sem_execute(i: int):
                async with semaphore:
                    return await _execute_single(i)

            tasks = [_sem_execute(i) for i in range(1, req.iterations + 1)]
            results = await asyncio.gather(*tasks)
            for it_res, body in results:
                iterations.append(it_res)
                raw_bodies.append(body)

        # Sort iterations by sequence index
        iterations.sort(key=lambda x: x.iteration)

        return cls._build_report_from_iterations(
            target_name=target_name,
            execution_mode=req.mode.value,
            iterations=iterations,
            raw_bodies=raw_bodies
        )

    @classmethod
    async def run_endpoint_multi_execution(
        cls,
        endpoint_id: int,
        req: EndpointMultiExecutionRequest,
        db: Session
    ) -> FlakinessReport:
        """Run repetitive multi-execution on a stored workspace endpoint."""
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Endpoint with ID {endpoint_id} not found."
            )

        target_name = f"Endpoint #{endpoint.id} [{endpoint.method}] {endpoint.path}"
        iterations: List[ExecutionIterationResult] = []
        raw_bodies: List[Any] = []

        endpoint_exec_req = EndpointExecutionRequest(
            request_override=req.request_override,
            options=ExecutionOptions(
                timeout_seconds=req.timeout_seconds,
                follow_redirects=True
            )
        )

        async def _execute_single(idx: int) -> Tuple[ExecutionIterationResult, Any]:
            ts = datetime.now(timezone.utc).isoformat()
            try:
                res: ExecutionResultResponse = await HttpDispatcherService.dispatch_endpoint(
                    project_id=endpoint.project_id,
                    endpoint_id=endpoint.id,
                    req=endpoint_exec_req,
                    db=db
                )
                status_code = res.status_code
                status_text = res.status_text
                elapsed = res.elapsed_ms
                body = res.body
                error = res.error
                is_success = res.is_success
            except Exception as exc:
                status_code = None
                status_text = "Execution Error"
                elapsed = 0.0
                body = None
                error = str(exc)
                is_success = False

            payload_hash = cls._compute_body_hash(body)
            iter_result = ExecutionIterationResult(
                iteration=idx,
                timestamp=ts,
                status_code=status_code,
                status_text=status_text,
                elapsed_ms=round(elapsed, 3),
                payload_hash=payload_hash,
                is_success=is_success,
                error=error
            )
            return iter_result, body

        if req.mode == ExecutionMode.SEQUENTIAL:
            for i in range(1, req.iterations + 1):
                if i > 1 and req.delay_ms > 0:
                    await asyncio.sleep(req.delay_ms / 1000.0)
                it_res, body = await _execute_single(i)
                iterations.append(it_res)
                raw_bodies.append(body)
        else:
            semaphore = asyncio.Semaphore(req.concurrency_limit)

            async def _sem_execute(i: int):
                async with semaphore:
                    return await _execute_single(i)

            tasks = [_sem_execute(i) for i in range(1, req.iterations + 1)]
            results = await asyncio.gather(*tasks)
            for it_res, body in results:
                iterations.append(it_res)
                raw_bodies.append(body)

        iterations.sort(key=lambda x: x.iteration)

        return cls._build_report_from_iterations(
            target_name=target_name,
            execution_mode=req.mode.value,
            iterations=iterations,
            raw_bodies=raw_bodies
        )

    @classmethod
    def analyze_batch(
        cls,
        req: AnalyzeBatchRequest
    ) -> FlakinessReport:
        """Perform statistical flakiness analysis on an existing batch of iteration results."""
        raw_bodies = [it.payload_hash for it in req.iterations]
        return cls._build_report_from_iterations(
            target_name=req.target_name or "Batch Analysis",
            execution_mode="batch_analysis",
            iterations=req.iterations,
            raw_bodies=raw_bodies
        )
