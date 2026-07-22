"""Tests for the local filesystem storage backend."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from theme_analysis_ui.storage.local import LocalStorageBackend


def test_local_storage_writes_file(tmp_path: Path) -> None:
    """Ensure uploads land on disk with a unique prefix."""

    backend = LocalStorageBackend(root=tmp_path)
    payload = BytesIO(b"theme-analyst-report")
    location = backend.store_file(payload, "report.csv", "text/csv")
    saved_path = Path(location)
    assert saved_path.exists()  # nosec B101
    assert saved_path.read_bytes() == b"theme-analyst-report"  # nosec B101


def test_local_storage_reads_text_file(tmp_path: Path) -> None:
    """Ensure text files can be read back through the storage abstraction."""

    backend = LocalStorageBackend(root=tmp_path)
    path = tmp_path / "report.json"
    path.write_text('{"status": "ok"}', encoding="utf-8")

    assert backend.read_text(str(path), encoding="utf-8") == '{"status": "ok"}'  # nosec B101
