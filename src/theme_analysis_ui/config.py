"""Configuration helpers for the Theme Analysis UI application.

The settings object centralises environment-derived options so unit tests can
inject deterministic values while deployments may override behaviour with
standard environment variables.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal, cast

FileStore = Literal["LOCAL", "GCP"]
ONS_DESIGN_SYSTEM_STYLESHEET = "https://cdn.ons.gov.uk/sdc/design-system/73.1.1/css/styles.css"


@dataclass(frozen=True)
class Settings:
    """Immutable settings container for the Flask application."""

    environment: str
    file_store: FileStore
    upload_dir: Path
    bucket_name: str | None
    secret_key: str
    ons_stylesheet_url: str = ONS_DESIGN_SYSTEM_STYLESHEET

    def as_dict(self) -> dict[str, str]:
        """Return a serialisable snapshot of the configuration.

        Returns:
            dict[str, str]: Dictionary containing human readable settings.
        """

        data = {
            "environment": self.environment,
            "file_store": self.file_store,
            "upload_dir": str(self.upload_dir),
            "ons_stylesheet_url": self.ons_stylesheet_url,
        }
        if self.bucket_name:
            data["bucket_name"] = self.bucket_name
        return data

    def ensure_local_target(self) -> None:
        """Create the upload directory when the local backend is selected."""

        if self.file_store == "LOCAL":
            self.upload_dir.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    """Load settings from environment variables with safe defaults.

    Returns:
        Settings: Configured settings ready for dependency injection.

    Raises:
        ValueError: If the selected storage backend is not supported or when a
            bucket name is missing for Google Cloud Storage deployments.
    """

    environment = os.getenv("FLASK_ENV", "development")
    raw_file_store = os.getenv("FILE_STORE", "LOCAL").upper()
    if raw_file_store not in {"LOCAL", "GCP"}:
        raise ValueError("FILE_STORE must be either 'LOCAL' or 'GCP'.")
    upload_dir = Path(os.getenv("UPLOAD_DIR", "uploads")).expanduser().resolve()
    bucket_name = os.getenv("BUCKET_NAME")
    secret_key = os.getenv("FLASK_SECRET_KEY", "theme-analysis-ui-dev-secret")

    file_store = cast(FileStore, raw_file_store)
    settings = Settings(
        environment=environment,
        file_store=file_store,
        upload_dir=upload_dir,
        bucket_name=bucket_name,
        secret_key=secret_key,
    )
    if settings.file_store == "GCP" and not settings.bucket_name:
        raise ValueError("BUCKET_NAME is required when FILE_STORE=GCP.")

    settings.ensure_local_target()
    return settings
