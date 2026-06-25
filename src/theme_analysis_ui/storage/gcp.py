"""Google Cloud Storage backend for the Theme Analysis UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol, cast
from uuid import uuid4

from google.auth.exceptions import DefaultCredentialsError
from google.cloud.storage import Bucket, Client
from werkzeug.utils import secure_filename

from .base import StorageBackend


class GCPClientProtocol(Protocol):
    """Minimal protocol for Cloud Storage client interactions."""

    def bucket(self, name: str) -> Bucket: ...


@dataclass
class GCPStorageBackend(StorageBackend):
    """Persist uploaded files to a Google Cloud Storage bucket."""

    bucket_name: str
    prefix: str | None = None
    client: GCPClientProtocol | None = None

    def get_client(self) -> GCPClientProtocol:
        """Lazily create a Cloud Storage client.

        Initialising the backend should not require Google credentials so the
        application can boot in environments where uploads are not yet needed.
        """

        if self.client is None:
            self.client = Client()
        return self.client

    def _build_blob_name(self, filename: str) -> str:
        """Build a safe blob name with optional prefix.

        Args:
            filename: Original filename provided by the user.

        Returns:
            A GCS-compatible blob path.
        """
        safe_name = secure_filename(filename) or "upload.bin"
        unique_name = f"{uuid4().hex}_{safe_name}"

        if self.prefix:
            return f"{self.prefix.strip('/')}/{unique_name}"
        return unique_name

    def _parse_gcs_uri(self, location: str) -> tuple[str, str]:
        """Parse a ``gs://`` URI into bucket and blob names."""

        if not location.startswith("gs://"):
            raise ValueError(f"Expected a gs:// URI, got: {location}")

        relative_path = location.removeprefix("gs://")
        if "/" not in relative_path:
            raise ValueError(f"Invalid GCS URI: {location}")

        bucket_name, blob_name = relative_path.split("/", 1)
        if not bucket_name or not blob_name:
            raise ValueError(f"Invalid GCS URI: {location}")

        return bucket_name, blob_name

    def store_file(
        self,
        source: BinaryIO,
        filename: str,
        content_type: str,
    ) -> str:
        """Upload the file to Cloud Storage and return the ``gs://`` URI.

        Args:
            source: File-like object to upload.
            filename: Original filename.
            content_type: MIME type of the file.

        Returns:
            The GCS URI of the uploaded file.

        Raises:
            RuntimeError: If GCP credentials are not configured.
        """
        blob_name = self._build_blob_name(filename)

        try:
            bucket = self.get_client().bucket(self.bucket_name)
        except DefaultCredentialsError as exc:  # pragma: no cover
            raise RuntimeError(
                "Google Cloud credentials are not configured. "
                "Set up Application Default Credentials for FILE_STORE=GCP."
            ) from exc

        blob = bucket.blob(blob_name)
        source.seek(0)
        blob.upload_from_file(source, content_type=content_type)

        return f"gs://{self.bucket_name}/{blob_name}"

    def read_text(self, location: str, *, encoding: str = "utf-8") -> str:
        """Read a text file from Google Cloud Storage."""

        bucket_name, blob_name = self._parse_gcs_uri(location)
        blob = self.get_client().bucket(bucket_name).blob(blob_name)
        return cast(str, blob.download_as_text(encoding=encoding))
