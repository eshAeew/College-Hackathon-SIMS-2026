"""Performance Benchmarking Service Layer."""
import asyncio
import logging
import time
from typing import List, Optional, Tuple
import httpx
from sqlalchemy.orm import Session

from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.schemas.performance import (
    AnalyzeLatencyBatchRequest,
    DirectBenchmarkRequest,
    EndpointBenchmarkRequest,
    PerformanceBenchmarkIteration,
    PerformanceReport,
    SLAPolicy,
)
from app.models.schemas.request_config import (
    DirectRequestBuilderRequest,
    RequestCompileOverride,
)
from app.services.http_dispatcher import HttpDispatcherService
from app.services.request_builder_service import RequestBuilderService
from app.utils.performance_calculator import (
    classify_latency_bucket,
    compute_latency_percentiles,
    evaluate_sla_policy,
)

logger = logging.getLogger("app.services.performance")


class PerformanceService:
    """Service orchestrating performance load benchmarks, statistical aggregation, and SLA grading."""

    @classmethod
    async def benchmark_direct(
        cls,
        req: DirectBenchmarkRequest,
        client: Optional[httpx.AsyncClient] = None
    ) -> PerformanceReport:
        """Run performance benchmark against an ad-hoc HTTP target."""
        builder_dto = DirectRequestBuilderRequest(
            base_url=req.base_url,
            method=req.method,
            path=req.path,
            path_params=req.path_params,
            query_params=req.query_params,
            headers=req.headers,
            body_type=req.body_type,
            body=req.body
        )

        httpx_req, compiled_dto = RequestBuilderService.compile_direct_request(builder_dto)

        iterations, wall_clock_seconds = await cls._execute_benchmark_runs(
            httpx_req=httpx_req,
            repetition_count=req.repetition_count,
            concurrency_limit=req.concurrency_limit,
            delay_ms=req.delay_ms,
            client=client
        )

        return cls._build_performance_report(
            target_url=compiled_dto.url,
            http_method=compiled_dto.method,
            iterations=iterations,
            wall_clock_seconds=wall_clock_seconds,
            sla_policy=req.sla_policy
        )

    @classmethod
    async def benchmark_endpoint(
        cls,
        endpoint_id: int,
        req: EndpointBenchmarkRequest,
        db: Session,
        client: Optional[httpx.AsyncClient] = None
    ) -> PerformanceReport:
        """Run performance benchmark against a stored workspace endpoint."""
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise ValueError(f"Endpoint #{endpoint_id} not found.")

        project = db.query(Project).filter(Project.id == endpoint.project_id).first()
        if not project:
            raise ValueError(f"Parent Project #{endpoint.project_id} not found.")

        overrides = RequestCompileOverride(
            path_params=req.path_params,
            query_params=req.query_params,
            headers=req.headers,
            body_type=req.body_type,
            body=req.body
        )

        httpx_req, compiled_dto = RequestBuilderService.compile_endpoint_request(
            project=project,
            endpoint=endpoint,
            overrides=overrides
        )

        # Default SLA policy if not overridden
        sla_policy = req.sla_policy or SLAPolicy(
            max_acceptable_latency_ms=endpoint.expected_status if endpoint.expected_status else 1500.0
        )

        iterations, wall_clock_seconds = await cls._execute_benchmark_runs(
            httpx_req=httpx_req,
            repetition_count=req.repetition_count,
            concurrency_limit=req.concurrency_limit,
            delay_ms=req.delay_ms,
            client=client
        )

        return cls._build_performance_report(
            target_url=compiled_dto.url,
            http_method=compiled_dto.method,
            iterations=iterations,
            wall_clock_seconds=wall_clock_seconds,
            sla_policy=sla_policy
        )

    @classmethod
    def analyze_batch(cls, req: AnalyzeLatencyBatchRequest) -> PerformanceReport:
        """Analyze pre-recorded latency values against an SLA policy without executing live HTTP requests."""
        latencies = req.latencies
        total_requests = len(latencies)
        failed_requests = req.error_count
        successful_requests = max(0, total_requests - failed_requests)
        error_rate_pct = round((failed_requests / total_requests * 100.0), 2) if total_requests > 0 else 0.0

        metrics = compute_latency_percentiles(latencies)
        sla_result = evaluate_sla_policy(
            metrics=metrics,
            sla_policy=req.sla_policy,
            total_requests=total_requests,
            error_count=failed_requests
        )

        iterations = [
            PerformanceBenchmarkIteration(
                iteration=idx + 1,
                status_code=200 if idx < successful_requests else 500,
                latency_ms=round(lat, 2),
                bucket=classify_latency_bucket(lat),
                success=idx < successful_requests
            )
            for idx, lat in enumerate(latencies)
        ]

        return PerformanceReport(
            target_url=None,
            http_method=None,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            error_rate_pct=error_rate_pct,
            throughput_rps=round(total_requests / (sum(latencies) / 1000.0), 2) if sum(latencies) > 0 else 0.0,
            metrics=metrics,
            sla_result=sla_result,
            iterations=iterations
        )

    @classmethod
    async def _execute_benchmark_runs(
        cls,
        httpx_req: httpx.Request,
        repetition_count: int,
        concurrency_limit: int,
        delay_ms: float,
        client: Optional[httpx.AsyncClient] = None
    ) -> Tuple[List[PerformanceBenchmarkIteration], float]:
        """Dispatch repeated benchmark executions sequentially or concurrently."""
        iterations: List[PerformanceBenchmarkIteration] = []
        start_wall_clock = time.perf_counter()

        if concurrency_limit <= 1:
            # Sequential execution with optional delay
            for idx in range(repetition_count):
                if idx > 0 and delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000.0)

                # Clone request for each run
                clone_req = httpx.Request(
                    method=httpx_req.method,
                    url=httpx_req.url,
                    headers=httpx_req.headers,
                    content=httpx_req.content
                )

                exec_res = await HttpDispatcherService.dispatch_httpx_request(
                    request=clone_req,
                    options=None,
                    client=client
                )

                lat = exec_res.elapsed_ms
                is_success = exec_res.status_code is not None and 200 <= exec_res.status_code < 300

                iterations.append(
                    PerformanceBenchmarkIteration(
                        iteration=idx + 1,
                        status_code=exec_res.status_code,
                        latency_ms=lat,
                        bucket=classify_latency_bucket(lat),
                        success=is_success
                    )
                )
        else:
            # Concurrent execution with semaphore rate-limiting
            semaphore = asyncio.Semaphore(concurrency_limit)

            async def _run_one(iteration_idx: int) -> PerformanceBenchmarkIteration:
                async with semaphore:
                    clone_req = httpx.Request(
                        method=httpx_req.method,
                        url=httpx_req.url,
                        headers=httpx_req.headers,
                        content=httpx_req.content
                    )
                    exec_res = await HttpDispatcherService.dispatch_httpx_request(
                        request=clone_req,
                        options=None,
                        client=client
                    )
                    lat = exec_res.elapsed_ms
                    is_success = exec_res.status_code is not None and 200 <= exec_res.status_code < 300
                    return PerformanceBenchmarkIteration(
                        iteration=iteration_idx,
                        status_code=exec_res.status_code,
                        latency_ms=lat,
                        bucket=classify_latency_bucket(lat),
                        success=is_success
                    )

            tasks = [_run_one(i + 1) for i in range(repetition_count)]
            results = await asyncio.gather(*tasks)
            iterations.extend(sorted(results, key=lambda x: x.iteration))

        wall_clock_seconds = time.perf_counter() - start_wall_clock
        return iterations, wall_clock_seconds

    @classmethod
    def _build_performance_report(
        cls,
        target_url: str,
        http_method: str,
        iterations: List[PerformanceBenchmarkIteration],
        wall_clock_seconds: float,
        sla_policy: SLAPolicy
    ) -> PerformanceReport:
        """Aggregate iteration telemetry and construct complete PerformanceReport."""
        latencies = [it.latency_ms for it in iterations]
        total_requests = len(iterations)
        successful_requests = sum(1 for it in iterations if it.success)
        failed_requests = total_requests - successful_requests
        error_rate_pct = round((failed_requests / total_requests * 100.0), 2) if total_requests > 0 else 0.0
        throughput_rps = round(total_requests / wall_clock_seconds, 2) if wall_clock_seconds > 0 else 0.0

        metrics = compute_latency_percentiles(latencies)
        sla_result = evaluate_sla_policy(
            metrics=metrics,
            sla_policy=sla_policy,
            total_requests=total_requests,
            error_count=failed_requests
        )

        return PerformanceReport(
            target_url=target_url,
            http_method=http_method,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            error_rate_pct=error_rate_pct,
            throughput_rps=throughput_rps,
            metrics=metrics,
            sla_result=sla_result,
            iterations=iterations
        )