import io
import json
import os
from collections.abc import Callable
from unittest.mock import patch
from wsgiref.types import StartResponse, WSGIEnvironment

from claude_service.wsgi import app


class _CapturedResponse:
    """Records the status and headers passed to a start_response call."""

    def __init__(self) -> None:
        self.status = ""
        self.headers: list[tuple[str, str]] = []


def _capturing_start_response() -> tuple[StartResponse, _CapturedResponse]:
    """Build a start_response callable that records its status and headers."""
    captured = _CapturedResponse()

    def start_response(
        status: str,
        headers: list[tuple[str, str]],
        exc_info: object = None,
    ) -> Callable[[bytes], object]:
        captured.status = status
        captured.headers = headers
        return lambda data: None

    return start_response, captured


def _graphql_environ(request_body: bytes) -> WSGIEnvironment:
    return {
        "PATH_INFO": "/graphql",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(request_body)),
        "wsgi.input": io.BytesIO(request_body),
    }


def _run_query(query: str) -> dict:
    start_response, _ = _capturing_start_response()
    body = json.dumps({"query": query}).encode("utf-8")
    result = app(_graphql_environ(body), start_response)
    return json.loads(b"".join(result))


def test_submit_prompt_mutation_creates_pending_job() -> None:
    start_response, captured = _capturing_start_response()
    request_body = json.dumps(
        {
            "query": (
                'mutation { claude { submitPrompt(prompt: "hello") '
                "{ id status prompt response error } } }"
            )
        }
    ).encode("utf-8")

    body = app(_graphql_environ(request_body), start_response)

    assert captured.status == "200 OK"
    parsed = json.loads(b"".join(body))
    job = parsed["data"]["claude"]["submitPrompt"]
    assert job["prompt"] == "hello"
    assert job["status"] == "PENDING"
    assert job["response"] is None
    assert job["error"] is None


def test_prompt_job_query_returns_submitted_job() -> None:
    submitted = _run_query('mutation { claude { submitPrompt(prompt: "hi") { id } } }')
    job_id = submitted["data"]["claude"]["submitPrompt"]["id"]

    result = _run_query(f'{{ claude {{ promptJob(id: "{job_id}") {{ id prompt }} }} }}')

    assert result["data"]["claude"]["promptJob"]["id"] == job_id
    assert result["data"]["claude"]["promptJob"]["prompt"] == "hi"


def test_prompt_job_query_returns_null_for_missing_id() -> None:
    result = _run_query('{ claude { promptJob(id: "999999") { id } } }')

    assert result["data"]["claude"]["promptJob"] is None


def test_pending_prompts_query_excludes_completed_jobs() -> None:
    first = _run_query('mutation { claude { submitPrompt(prompt: "a") { id } } }')
    first_id = first["data"]["claude"]["submitPrompt"]["id"]
    second = _run_query('mutation { claude { submitPrompt(prompt: "b") { id } } }')
    second_id = second["data"]["claude"]["submitPrompt"]["id"]

    _run_query(
        f'mutation {{ claude {{ completePrompt(id: "{first_id}", '
        'response: "done") { id } } }'
    )

    result = _run_query("{ claude { pendingPrompts { id } } }")
    ids = [job["id"] for job in result["data"]["claude"]["pendingPrompts"]]

    assert ids == [second_id]


def test_complete_prompt_mutation_sets_completed_status_and_response() -> None:
    created = _run_query('mutation { claude { submitPrompt(prompt: "a") { id } } }')
    job_id = created["data"]["claude"]["submitPrompt"]["id"]

    result = _run_query(
        f'mutation {{ claude {{ completePrompt(id: "{job_id}", '
        'response: "the answer") { id status response } } }'
    )
    job = result["data"]["claude"]["completePrompt"]

    assert job["status"] == "COMPLETED"
    assert job["response"] == "the answer"


def test_complete_prompt_mutation_errors_for_unknown_id() -> None:
    result = _run_query(
        'mutation { claude { completePrompt(id: "999999", response: "x") { id } } }'
    )

    assert result["data"] is None
    assert any("not found" in error["message"] for error in result["errors"])


def test_fail_prompt_mutation_sets_failed_status_and_error() -> None:
    created = _run_query('mutation { claude { submitPrompt(prompt: "a") { id } } }')
    job_id = created["data"]["claude"]["submitPrompt"]["id"]

    result = _run_query(
        f'mutation {{ claude {{ failPrompt(id: "{job_id}", '
        'error: "claude timed out") { id status error } } }'
    )
    job = result["data"]["claude"]["failPrompt"]

    assert job["status"] == "FAILED"
    assert job["error"] == "claude timed out"


def test_fail_prompt_mutation_errors_for_unknown_id() -> None:
    result = _run_query(
        'mutation { claude { failPrompt(id: "999999", error: "x") { id } } }'
    )

    assert result["data"] is None
    assert any("not found" in error["message"] for error in result["errors"])


def test_graphql_service_sdl_query_returns_federation_sdl() -> None:
    result = _run_query("{ _service { sdl } }")

    sdl = result["data"]["_service"]["sdl"]
    assert isinstance(sdl, str) and len(sdl) > 0


def test_graphql_route_returns_errors_for_invalid_json_body() -> None:
    start_response, captured = _capturing_start_response()

    request_body = b"not valid json {{{"
    body = app(_graphql_environ(request_body), start_response)

    assert captured.status == "200 OK"
    assert json.loads(b"".join(body)) == {"errors": [{"message": "invalid JSON body"}]}


def test_version_route_returns_commit_sha_from_env() -> None:
    start_response, captured = _capturing_start_response()

    environ = {"PATH_INFO": "/version", "REQUEST_METHOD": "GET"}
    with patch.dict(os.environ, {"COMMIT_SHA": "abc1234"}):
        body = app(environ, start_response)

    assert captured.status == "200 OK"
    assert json.loads(b"".join(body)) == {"commit_sha": "abc1234"}
    assert ("Content-Type", "application/json") in captured.headers


def test_unknown_route_returns_404() -> None:
    start_response, captured = _capturing_start_response()

    environ = {"PATH_INFO": "/nope", "REQUEST_METHOD": "GET"}
    body = app(environ, start_response)

    assert captured.status == "404 Not Found"
    assert json.loads(b"".join(body)) == {"error": "not found"}


def test_graphql_get_request_returns_404() -> None:
    start_response, captured = _capturing_start_response()

    environ = {"PATH_INFO": "/graphql", "REQUEST_METHOD": "GET"}
    body = app(environ, start_response)

    assert captured.status == "404 Not Found"
    assert json.loads(b"".join(body)) == {"error": "not found"}
