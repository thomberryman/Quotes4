from app.jobs.registry import REGISTERED_JOBS, jobs_by_queue_name


def test_all_expected_queues_are_registered() -> None:
    registered = {job.queue_name for job in REGISTERED_JOBS}
    assert registered == {
        "pdf_parse",
        "ceta_import",
        "forecast_recalc",
        "comparables_refresh",
        "dashboard_refresh",
        "notifications",
    }


def test_registry_lookup_uses_queue_names() -> None:
    registry = jobs_by_queue_name()

    assert registry["pdf_parse"].name == "quote-pdf-parse"
    assert registry["forecast_recalc"].retry_backoff_seconds == 15
    assert registry["comparables_refresh"].retry_backoff_seconds == 30
