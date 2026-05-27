"""Prometheus-compatible metrics endpoint."""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ..state import quality_metrics, _derive_quality_metrics

router = APIRouter(tags=["health"])


def _prometheus_format(data: dict[str, float | int]) -> str:
    """Convert metrics dict to Prometheus exposition format."""
    lines: list[str] = []
    for key, value in sorted(data.items()):
        metric_name = f"starsorty_{key}"
        lines.append(f"# TYPE {metric_name} gauge")
        if isinstance(value, float):
            lines.append(f"{metric_name} {value:.6f}")
        else:
            lines.append(f"{metric_name} {value}")
    return "\n".join(lines) + "\n"


@router.get("/metrics", response_class=PlainTextResponse, summary="Prometheus metrics")
async def prometheus_metrics():
    """Expose system metrics in Prometheus exposition format."""
    data = _derive_quality_metrics(dict(quality_metrics))
    return _prometheus_format(data)
