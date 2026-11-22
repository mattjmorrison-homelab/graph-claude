"""SQLite storage for the Claude prompt queue.

One connection per call, opened and closed around each statement — this
service has no long-lived request/response object to hang a shared
connection off of (plain WSGI, see wsgi.py), and SQLite's file-level
locking makes short-lived connections the simplest safe option under
gunicorn's multi-worker model.
"""

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DB_PATH = os.environ.get("CLAUDE_SERVICE_DB_PATH", "/data/claude-service.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prompt_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    response TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
"""

_SELECT_COLUMNS = "id, prompt, status, response, error, created_at"


@dataclass
class PromptJobRow:
    id: int
    prompt: str
    status: str
    response: str | None
    error: str | None
    created_at: str


def _connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute(_SCHEMA)
    return connection


def _row_to_prompt_job(
    row: tuple[int, str, str, str | None, str | None, str],
) -> PromptJobRow:
    return PromptJobRow(
        id=row[0],
        prompt=row[1],
        status=row[2],
        response=row[3],
        error=row[4],
        created_at=row[5],
    )


def insert_prompt_job(prompt: str, created_at: str) -> PromptJobRow:
    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT INTO prompt_jobs (prompt, status, created_at) "
            "VALUES (?, 'PENDING', ?)",
            (prompt, created_at),
        )
        connection.commit()
        job_id = cursor.lastrowid
    finally:
        connection.close()
    assert job_id is not None
    job = get_prompt_job(job_id)
    assert job is not None
    return job


def get_prompt_job(job_id: int) -> PromptJobRow | None:
    connection = _connect()
    try:
        row = connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM prompt_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else _row_to_prompt_job(row)


def pending_prompts() -> list[PromptJobRow]:
    connection = _connect()
    try:
        rows = connection.execute(
            f"SELECT {_SELECT_COLUMNS} FROM prompt_jobs "
            "WHERE status = 'PENDING' ORDER BY created_at ASC"
        ).fetchall()
    finally:
        connection.close()
    return [_row_to_prompt_job(row) for row in rows]


def complete_prompt_job(job_id: int, response: str) -> PromptJobRow | None:
    connection = _connect()
    try:
        connection.execute(
            "UPDATE prompt_jobs SET status = 'COMPLETED', response = ? WHERE id = ?",
            (response, job_id),
        )
        connection.commit()
    finally:
        connection.close()
    return get_prompt_job(job_id)


def fail_prompt_job(job_id: int, error: str) -> PromptJobRow | None:
    connection = _connect()
    try:
        connection.execute(
            "UPDATE prompt_jobs SET status = 'FAILED', error = ? WHERE id = ?",
            (error, job_id),
        )
        connection.commit()
    finally:
        connection.close()
    return get_prompt_job(job_id)
