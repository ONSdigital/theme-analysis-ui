"""Tests for configuration loading behaviour."""

from __future__ import annotations

from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from theme_analysis_ui.config import Settings, load_settings

TEST_APP_KEY = "unit-test-example-key"  # pragma: allowlist secret


def test_load_settings_defaults_to_local(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Ensure the loader selects the local backend when unspecified."""

    monkeypatch.delenv("FILE_STORE", raising=False)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    settings = load_settings()
    assert settings.file_store == "LOCAL"  # nosec B101
    assert settings.upload_dir == tmp_path.resolve()  # nosec B101


def test_settings_record_bucket_name_when_configured(tmp_path: Path) -> None:
    """Ensure the settings dataclass exposes bucket metadata."""

    settings = Settings(
        environment="test",
        file_store="GCP",
        upload_dir=tmp_path / "uploads",
        bucket_name="test-bucket",
        secret_key=TEST_APP_KEY,  # nosec B105
    )
    details = settings.as_dict()
    assert details["bucket_name"] == "test-bucket"  # nosec B101
