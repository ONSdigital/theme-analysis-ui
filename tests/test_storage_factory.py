"""Tests covering storage factory behaviour and the GCP backend."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from _pytest.monkeypatch import MonkeyPatch

from theme_analysis_ui.config import Settings
from theme_analysis_ui.storage.factory import build_storage_backend
from theme_analysis_ui.storage.gcp import GCPStorageBackend
from theme_analysis_ui.storage.local import LocalStorageBackend

TEST_APP_KEY = "unit-test-example-key"  # pragma: allowlist secret


class DummyBlob:
    """Fake Cloud Storage blob capturing upload calls."""

    def __init__(self) -> None:
        self.uploads: list[tuple[bytes, str]] = []

    def upload_from_file(self, source: BinaryIO, content_type: str) -> None:
        self.uploads.append((source.read(), content_type))


class DummyBucket:
    """Fake Cloud Storage bucket returning DummyBlob instances."""

    def __init__(self) -> None:
        self.requested_name: str | None = None
        self.blob_instance = DummyBlob()

    def blob(self, name: str) -> DummyBlob:
        self.requested_name = name
        return self.blob_instance


class DummyClient:
    """Fake Cloud Storage client used for unit tests."""

    def __init__(self) -> None:
        self.requested_bucket: str | None = None
        self.bucket_instance = DummyBucket()

    def bucket(self, name: str) -> DummyBucket:
        self.requested_bucket = name
        return self.bucket_instance


def test_factory_returns_local_backend(tmp_path: Path) -> None:
    """Ensure local settings produce a LocalStorageBackend instance."""

    settings = Settings(
        environment="test",
        file_store="LOCAL",
        upload_dir=tmp_path,
        bucket_name=None,
        secret_key=TEST_APP_KEY,  # nosec B105
    )
    backend = build_storage_backend(settings)
    assert isinstance(backend, LocalStorageBackend)  # nosec B101


def test_factory_returns_gcp_backend(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Ensure GCP settings instantiate the Cloud Storage backend."""

    settings = Settings(
        environment="test",
        file_store="GCP",
        upload_dir=tmp_path,
        bucket_name="demo-bucket",
        secret_key=TEST_APP_KEY,  # nosec B105
    )
    sentinel = object()

    def fake_backend(bucket_name: str) -> object:
        assert bucket_name == "demo-bucket"  # nosec B101
        return sentinel

    monkeypatch.setattr(
        "theme_analysis_ui.storage.factory.GCPStorageBackend",
        fake_backend,
    )
    backend = build_storage_backend(settings)
    assert backend is sentinel  # nosec B101


def test_gcp_backend_initialisation_is_lazy(monkeypatch: MonkeyPatch) -> None:
    """Ensure backend creation does not require ADC until upload time."""

    class ExplodingClient:
        def __init__(self) -> None:
            raise AssertionError("Client should not be built during backend init")

    monkeypatch.setattr("theme_analysis_ui.storage.gcp.storage.Client", ExplodingClient)
    backend = GCPStorageBackend(bucket_name="demo-bucket")
    assert backend.client is None  # nosec B101


def test_gcp_backend_uploads_via_dummy_client() -> None:
    """Ensure the Google Cloud Storage backend streams bytes to the client."""

    client = DummyClient()
    backend = GCPStorageBackend(bucket_name="demo-bucket", client=client)
    location = backend.store_file(BytesIO(b"gcp"), "analysis.csv", "text/csv")
    assert location.startswith("gs://demo-bucket/uploads/")  # nosec B101
    assert client.requested_bucket == "demo-bucket"  # nosec B101
    assert client.bucket_instance.requested_name is not None  # nosec B101
    data, content_type = client.bucket_instance.blob_instance.uploads[0]
    assert data == b"gcp"  # nosec B101
    assert content_type == "text/csv"  # nosec B101
