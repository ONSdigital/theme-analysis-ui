"""Tests covering the upload and login routes."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from typing import BinaryIO, cast

from flask.testing import FlaskClient
import pytest
from werkzeug.security import generate_password_hash
import yaml

from theme_analysis_ui.app import create_app
from theme_analysis_ui.config import Settings
from theme_analysis_ui.routes import ui as ui_routes
from theme_analysis_ui.storage.local import LocalStorageBackend

TEST_APP_KEY = "unit-test-example-key"  # pragma: allowlist secret
TEST_PASSWORD = "example-password"  # nosec B105  # pragma: allowlist secret


class RecordingLocalStorageBackend(LocalStorageBackend):
    """Local storage backend that records uploaded payloads for assertions."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.calls: list[tuple[bytes, str, str]] = []

    def store_file(self, source: BinaryIO, filename: str, content_type: str) -> str:
        source.seek(0)
        data = source.read()
        self.calls.append((data, filename, content_type))
        source.seek(0)
        return super().store_file(source, filename, content_type)


@pytest.fixture(autouse=True)
def stub_template_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub template rendering to avoid external ONS template dependencies in tests."""

    def fake_render_template(template_name: str, **context: object) -> str:
        raw_errors = context.get("errors")
        errors = cast(list[str], raw_errors) if isinstance(raw_errors, list) else []
        errors_text = "|".join(errors)
        return f"template={template_name};errors={errors_text};context={context}"

    monkeypatch.setattr(ui_routes, "render_template", fake_render_template)


@pytest.fixture()
def test_client(tmp_path: Path) -> tuple[FlaskClient, RecordingLocalStorageBackend]:
    """Return a configured Flask test client and storage backend."""

    settings = Settings(
        environment="test",
        file_store="LOCAL",
        upload_dir=tmp_path,
        bucket_name=None,
        secret_key=TEST_APP_KEY,  # nosec B105
    )
    storage = RecordingLocalStorageBackend(root=tmp_path / "uploads")
    app = create_app(settings=settings, storage_backend=storage)
    app.testing = True
    return app.test_client(), storage


def test_login_route_renders_template(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure the login route returns the expected template response."""

    client, _ = test_client
    response = client.get("/login")
    assert response.status_code == 200  # nosec B101
    html = response.get_data(as_text=True)
    assert "template=login.html" in html  # nosec B101


def test_post_upload_without_file_returns_error(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure the service rejects submissions that skip file selection."""

    client, storage = test_client
    with client.session_transaction() as flask_session:
        flask_session[ui_routes.SESSION_USER_KEY] = "user@example.com"
    response = client.post("/upload", data={})
    assert response.status_code == 400  # nosec B101
    assert not storage.calls  # nosec B101
    page = response.get_data(as_text=True)
    assert "template=upload_theme_file.html" in page  # nosec B101
    assert "Select a file before continuing." in page  # nosec B101


def test_post_upload_persists_file_via_storage_backend(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure uploads reach the configured storage backend."""

    client, storage = test_client
    with client.session_transaction() as flask_session:
        flask_session[ui_routes.SESSION_USER_KEY] = "user@example.com"
    response = client.post(
        "/upload",
        data={
            "file": (BytesIO(b"content"), "analysis.csv"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200  # nosec B101
    assert storage.calls  # nosec B101
    payload, filename, content_type = storage.calls[0]
    assert payload == b"content"  # nosec B101
    assert filename == "analysis.csv"  # nosec B101
    assert content_type == "text/csv"  # nosec B101
    payload_html = response.get_data(as_text=True)
    assert "analysis.csv" in payload_html  # nosec B101


def test_post_upload_creates_metadata_yaml(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure a YAML sidecar file is written with the expected structure."""

    client, storage = test_client
    with client.session_transaction() as flask_session:
        flask_session[ui_routes.SESSION_USER_KEY] = "user@example.com"
        flask_session["meta"] = {"question": "How satisfied are you?"}
    response = client.post(
        "/upload",
        data={
            "file": (BytesIO(b"content"), "responses.csv"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200  # nosec B101
    stored_files = list(storage.root.iterdir())
    csv_files = [path for path in stored_files if path.suffix == ".csv"]
    yml_files = [path for path in stored_files if path.suffix == ".yml"]
    assert len(csv_files) == 1  # nosec B101
    assert len(yml_files) == 1  # nosec B101
    assert csv_files[0].stem == yml_files[0].stem  # nosec B101
    yaml_payload = yaml.safe_load(yml_files[0].read_text())
    theme_record = yaml_payload["theme_record"]
    assert theme_record["question"] == "How satisfied are you?"  # nosec B101
    assert theme_record["supporting_data"] == str(csv_files[0])  # nosec B101
    assert theme_record["survey"] == ui_routes.DEFAULT_SURVEY  # nosec B101
    assert theme_record["division"] == ui_routes.DEFAULT_DIVISION  # nosec B101
    assert theme_record["team"] == ui_routes.DEFAULT_TEAM  # nosec B101
    assert theme_record["survey_description"] == ui_routes.DEFAULT_SURVEY_DESCRIPTION  # nosec B101
    with client.session_transaction() as flask_session:
        session_meta = flask_session["meta"]
    assert session_meta["survey"] == ui_routes.DEFAULT_SURVEY  # nosec B101
    assert session_meta["division"] == ui_routes.DEFAULT_DIVISION  # nosec B101
    assert session_meta["team"] == ui_routes.DEFAULT_TEAM  # nosec B101
    assert session_meta["survey_description"] == ui_routes.DEFAULT_SURVEY_DESCRIPTION  # nosec B101
    page = response.get_data(as_text=True)
    assert str(yml_files[0]) in page  # nosec B101


def test_post_upload_uses_session_metadata_values(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure session-provided metadata overrides the defaults."""

    client, storage = test_client
    custom_meta = {
        "survey": "Pulse Satisfaction",
        "division": "Digital Services",
        "team": "Insights",
        "survey_description": "Bi-weekly pulse measuring employee sentiment.",
        "question": "Describe your team's current workload.",
        "contact": "insights@example.com",
        "wave": "2026-Q1",
    }
    with client.session_transaction() as flask_session:
        flask_session[ui_routes.SESSION_USER_KEY] = "user@example.com"
        flask_session["meta"] = custom_meta.copy()
    response = client.post(
        "/upload",
        data={"file": (BytesIO(b"content"), "team.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200  # nosec B101
    stored_files = list(storage.root.iterdir())
    yml_files = [path for path in stored_files if path.suffix == ".yml"]
    assert len(yml_files) == 1  # nosec B101
    yaml_payload = yaml.safe_load(yml_files[0].read_text())
    theme_record = yaml_payload["theme_record"]
    for key, value in custom_meta.items():
        assert theme_record[key] == value  # nosec B101
    with client.session_transaction() as flask_session:
        assert flask_session["meta"]["survey"] == custom_meta["survey"]  # nosec B101
        assert flask_session["meta"]["division"] == custom_meta["division"]  # nosec B101
        assert flask_session["meta"]["team"] == custom_meta["team"]  # nosec B101
        assert (
            flask_session["meta"]["survey_description"] == custom_meta["survey_description"]
        )  # nosec B101


def test_login_renders_sign_in_form(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure the login route renders the sign in form."""

    client, _ = test_client
    response = client.get("/login")
    assert response.status_code == 200  # nosec B101
    body = response.get_data(as_text=True)
    assert "Sign in" in body  # nosec B101
    assert "template=login.html" in body  # nosec B101


def test_unauthenticated_user_is_redirected_to_login(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure unauthenticated requests are redirected before rendering protected routes."""

    client, _ = test_client
    response = client.get("/theme_meta")
    assert response.status_code == 302  # nosec B101
    assert response.headers["Location"].endswith("/login")  # nosec B101


def test_check_login_rejects_unknown_user(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure unknown users cannot authenticate."""

    client, _ = test_client
    client.application.config["auth_users_provider"] = lambda: {
        "known.user@example.com": TEST_PASSWORD
    }
    response = client.post(
        "/check_login",
        data={
            "username": "missing.user@example.com",
            "password": TEST_PASSWORD,  # pragma: allowlist secret
        },
    )
    assert response.status_code == 401  # nosec B101
    assert "Invalid email address or password." in response.get_data(as_text=True)  # nosec B101


def test_check_login_accepts_known_user_and_redirects(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure valid users are authenticated and redirected to the originally requested path."""

    client, _ = test_client
    client.application.config["auth_users_provider"] = lambda: {
        "known.user@example.com": TEST_PASSWORD
    }
    with client.session_transaction() as flask_session:
        flask_session[ui_routes.POST_LOGIN_REDIRECT_KEY] = "/theme_meta"

    response = client.post(
        "/check_login",
        data={"username": "known.user@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 302  # nosec B101
    assert response.headers["Location"].endswith("/theme_meta")  # nosec B101
    with client.session_transaction() as flask_session:
        assert flask_session[ui_routes.SESSION_USER_KEY] == "known.user@example.com"  # nosec B101


def test_load_registered_users_supports_dictionary_payload(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure dict payloads from users.json are normalised."""

    client, _ = test_client
    client.application.config["auth_users_provider"] = lambda: {" USER@Example.com ": "plain-text"}
    with client.application.test_request_context("/"):
        users = ui_routes._load_registered_users()
    assert users == {" USER@Example.com ": "plain-text"}  # nosec B101


def test_load_registered_users_reads_gcp_list_payload(
    test_client: tuple[FlaskClient, RecordingLocalStorageBackend]
) -> None:
    """Ensure list payloads are parsed when loaded via GCP backend."""

    class FakeBlob:
        def download_as_text(self) -> str:
            return json.dumps(
                [
                    {
                        "email": "person@example.com",
                        "password": TEST_PASSWORD,
                    },
                    {"username": "ignored@example.com"},
                ]
            )

    class FakeBucket:
        def blob(self, _: str) -> FakeBlob:
            return FakeBlob()

    class FakeClient:
        def bucket(self, _: str) -> FakeBucket:
            return FakeBucket()

    gcp_backend = ui_routes.GCPStorageBackend(bucket_name="bucket", client=FakeClient())
    client, _ = test_client
    client.application.config["storage_backend"] = gcp_backend
    client.application.config["auth_users_provider"] = None
    settings = client.application.config["settings"]
    client.application.config["settings"] = Settings(
        environment=settings.environment,
        file_store=settings.file_store,
        upload_dir=settings.upload_dir,
        bucket_name="bucket",
        secret_key=settings.secret_key,
    )

    with client.application.test_request_context("/"):
        users = ui_routes._load_registered_users()
    assert users == {"person@example.com": TEST_PASSWORD}  # nosec B101


def test_credentials_match_supports_password_hashes() -> None:
    """Ensure hashed passwords are validated with werkzeug helpers."""

    password = TEST_PASSWORD
    users = {"person@example.com": generate_password_hash(password)}
    assert ui_routes._credentials_match(users, "person@example.com", password)  # nosec B101
    assert not ui_routes._credentials_match(users, "person@example.com", "wrong")  # nosec B101
