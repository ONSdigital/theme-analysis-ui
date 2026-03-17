"""Factory helpers for creating storage backends."""

from __future__ import annotations

from ..config import Settings
from .base import StorageBackend
from .gcp import GCPStorageBackend
from .local import LocalStorageBackend


def build_storage_backend(settings: Settings) -> StorageBackend:
    """Construct the correct storage backend for the provided settings.

    Args:
        settings (Settings): Application configuration.

    Returns:
        StorageBackend: Backend instance ready to accept uploads.
    """

    if settings.file_store == "GCP":
        return GCPStorageBackend(bucket_name=settings.bucket_name or "")
    return LocalStorageBackend(root=settings.upload_dir)
