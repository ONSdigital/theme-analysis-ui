"""Google Cloud Storage backend for the Theme Analysis UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol
from uuid import uuid4

from google.auth.exceptions import DefaultCredentialsError
from google.cloud import storage
from werkzeug.utils import secure_filename

from .base import StorageBackend


class GCPClientProtocol(Protocol):
    """Minimal protocol for Cloud Storage client interactions."""

    def bucket(self, name: str) -> storage.Bucket: ...


@dataclass
class GCPStorageBackend(StorageBackend):
    """Persist uploaded files to a Google Cloud Storage bucket."""

    bucket_name: str
    prefix: str = "uploads"
    client: GCPClientProtocol | None = None

    def get_client(self) -> GCPClientProtocol:
        """Lazily create a Cloud Storage client.

        Initialising the backend should not require Google credentials so the
        application can boot in environments where uploads are not yet needed.
        """

        if self.client is None:
            self.client = storage.Client()
        return self.client

    def store_file(self, source: BinaryIO, filename: str, content_type: str) -> str:  # noqa: D401
        """Upload the file to Cloud Storage and return the ``gs://`` URI."""

        safe_name = secure_filename(filename) or "upload.bin"
        blob_name = f"{self.prefix}/{uuid4().hex}_{safe_name}"

        try:
            bucket = self.get_client().bucket(self.bucket_name)
        except DefaultCredentialsError as exc:  # pragma: no cover - env-specific
            raise RuntimeError(
                "Google Cloud credentials are not configured. "
                "Set up Application Default Credentials for FILE_STORE=GCP."
            ) from exc

        blob = bucket.blob(blob_name)
        source.seek(0)
        blob.upload_from_file(source, content_type=content_type)
        return f"gs://{self.bucket_name}/{blob_name}"
