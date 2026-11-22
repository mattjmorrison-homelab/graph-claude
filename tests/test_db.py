from claude_service import db


def test_insert_prompt_job_creates_pending_row_with_given_fields() -> None:
    job = db.insert_prompt_job(
        prompt="summarize this", created_at="2026-11-10T00:00:00+00:00"
    )

    assert job.prompt == "summarize this"
    assert job.created_at == "2026-11-10T00:00:00+00:00"
    assert job.status == "PENDING"
    assert job.response is None
    assert job.error is None
    assert job.id > 0


def test_get_prompt_job_returns_none_for_missing_id() -> None:
    assert db.get_prompt_job(999) is None


def test_pending_prompts_excludes_completed_and_failed_rows() -> None:
    pending = db.insert_prompt_job(
        prompt="pending one", created_at="2026-11-10T00:00:00+00:00"
    )
    completed = db.insert_prompt_job(
        prompt="completed one", created_at="2026-11-10T00:01:00+00:00"
    )
    failed = db.insert_prompt_job(
        prompt="failed one", created_at="2026-11-10T00:02:00+00:00"
    )
    db.complete_prompt_job(completed.id, "done")
    db.fail_prompt_job(failed.id, "boom")

    jobs = db.pending_prompts()

    assert [row.id for row in jobs] == [pending.id]


def test_pending_prompts_orders_oldest_first() -> None:
    first = db.insert_prompt_job(prompt="first", created_at="2026-11-10T00:00:00+00:00")
    second = db.insert_prompt_job(
        prompt="second", created_at="2026-11-10T01:00:00+00:00"
    )

    jobs = db.pending_prompts()

    assert [row.id for row in jobs] == [first.id, second.id]


def test_complete_prompt_job_sets_status_and_response() -> None:
    job = db.insert_prompt_job(
        prompt="summarize this", created_at="2026-11-10T00:00:00+00:00"
    )

    completed = db.complete_prompt_job(job.id, "here is the summary")

    assert completed is not None
    assert completed.status == "COMPLETED"
    assert completed.response == "here is the summary"
    assert completed.error is None


def test_complete_prompt_job_returns_none_for_missing_id() -> None:
    assert db.complete_prompt_job(999, "response") is None


def test_fail_prompt_job_sets_status_and_error() -> None:
    job = db.insert_prompt_job(
        prompt="summarize this", created_at="2026-11-10T00:00:00+00:00"
    )

    failed = db.fail_prompt_job(job.id, "claude timed out")

    assert failed is not None
    assert failed.status == "FAILED"
    assert failed.error == "claude timed out"
    assert failed.response is None


def test_fail_prompt_job_returns_none_for_missing_id() -> None:
    assert db.fail_prompt_job(999, "error") is None
