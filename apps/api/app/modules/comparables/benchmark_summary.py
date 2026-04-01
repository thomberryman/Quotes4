from __future__ import annotations

from app.models import ProjectBenchmarkSummary
from app.modules.comparables.schemas import BenchmarkSummary, DisciplineBenchmarkSummary


def _to_float(value: object | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def build_benchmark_summary(
    benchmark_summary: ProjectBenchmarkSummary | None,
) -> BenchmarkSummary | None:
    if benchmark_summary is None:
        return None

    discipline_summaries = sorted(
        benchmark_summary.discipline_summaries,
        key=lambda item: ((item.discipline.name if item.discipline else ""), item.id),
    )
    return BenchmarkSummary(
        source_quote_version_id=benchmark_summary.source_quote_version_id,
        currency_code=benchmark_summary.currency_code,
        quoted_amount=_to_float(benchmark_summary.quoted_amount) or 0,
        actual_amount=_to_float(benchmark_summary.actual_amount),
        quote_to_actual_variance_amount=_to_float(
            benchmark_summary.quote_to_actual_variance_amount
        ),
        quote_to_actual_variance_pct=_to_float(benchmark_summary.quote_to_actual_variance_pct),
        actuals_status=benchmark_summary.actuals_status.value,
        actuals_as_of_date=(
            benchmark_summary.actuals_as_of_date.isoformat()
            if benchmark_summary.actuals_as_of_date is not None
            else None
        ),
        discipline_summaries=[
            DisciplineBenchmarkSummary(
                discipline_id=(
                    summary.discipline.code
                    if summary.discipline is not None
                    else summary.discipline_id
                ),
                discipline_name=summary.discipline.name if summary.discipline else None,
                quoted_amount=_to_float(summary.quoted_amount) or 0,
                actual_amount=_to_float(summary.actual_amount),
                quote_to_actual_variance_amount=_to_float(
                    summary.quote_to_actual_variance_amount
                ),
                quote_to_actual_variance_pct=_to_float(
                    summary.quote_to_actual_variance_pct
                ),
                actuals_status=summary.actuals_status.value,
            )
            for summary in discipline_summaries
        ],
    )
