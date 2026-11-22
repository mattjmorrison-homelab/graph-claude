from pathlib import Path

import pytest

from claude_service import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every test at its own throwaway SQLite file instead of the
    real CLAUDE_SERVICE_DB_PATH default, so tests never share or pollute state.
    """
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
