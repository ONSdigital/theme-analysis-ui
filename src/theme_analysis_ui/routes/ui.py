"""User facing routes for uploads and authentication flows."""

from __future__ import annotations

from datetime import datetime
import hmac
from http import HTTPStatus
import json
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, cast

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask import Response as ResponseType
from flask.typing import ResponseReturnValue
from werkzeug.security import check_password_hash
import yaml

from ..storage import GCPStorageBackend, StorageBackend

DEFAULT_SURVEY = "Example Survey"
DEFAULT_DIVISION = "Example Division"
DEFAULT_TEAM = "Example Team"
DEFAULT_SURVEY_DESCRIPTION = "Example Survey Description"

ui_blueprint = Blueprint("ui", __name__)

SESSION_USER_KEY = "authenticated_user"
POST_LOGIN_REDIRECT_KEY = "post_login_redirect"
ALLOWED_REDIRECT_PREFIXES = ["/index", "/theme_meta", "/upload", "/confirm"]


@ui_blueprint.before_app_request
def enforce_login() -> ResponseReturnValue | None:
    """Ensure unauthenticated users are redirected to the sign-in page."""

    if request.endpoint in {"ui.login", "ui.check_login", "static"}:
        return None
    if session.get(SESSION_USER_KEY):
        return None

    if request.method == "GET" and any(
        request.path.startswith(p) for p in ALLOWED_REDIRECT_PREFIXES
    ):
        session[POST_LOGIN_REDIRECT_KEY] = request.full_path.rstrip("?")
    return redirect(url_for("ui.login"))


@ui_blueprint.get("/")
def index() -> ResponseReturnValue:
    """Render the upload form that adopts the ONS Design System."""
    return render_template("index.html")


@ui_blueprint.get("/theme_meta")
def theme_meta() -> ResponseReturnValue:
    """Render the theme metadata form that adopts the ONS Design System."""

    return render_template(
        "theme_meta.html",
        page_title="Theme analysis metadata",
    )


@ui_blueprint.route("/save_meta", methods=["POST"])
def save_meta() -> ResponseType | str | tuple[str, int]:
    """Saves the response to theme metadata.

    Returns:
        ResponseType | str | tuple[str, int]: Redirect or error response.
    """

    if "meta" not in session:
        session["meta"] = {}

    session["meta"]["contact"] = session.get(SESSION_USER_KEY, "unknown user")
    session["meta"]["question"] = request.form.get("meta_response")
    session.modified = True  # Ensure session is saved even if only modified in-place

    print(f"Received response for question '{session['meta']['question']}'")

    return render_template(
        "upload_theme_file.html",
        page_title="Theme analysis uploads",
        page_config=None,
        meta_question=session["meta"]["question"],
        errors=[],
        upload_result=None,
    )


@ui_blueprint.post("/upload")
def handle_upload() -> ResponseReturnValue:
    """Process a submitted file upload request."""

    upload = request.files.get("file")
    errors: list[str] = []
    if upload is None or not upload.filename or upload.filename.strip() == "":
        errors.append("Select a file before continuing.")
        return (
            render_template(
                "upload_theme_file.html",
                page_title="Theme analysis uploads",
                page_config=None,
                meta_question=session.get("meta", {}).get("question", "the selected question"),
                errors=errors,
                upload_result=None,
            ),
            HTTPStatus.BAD_REQUEST,
        )

    filename = upload.filename
    storage: StorageBackend = current_app.config["storage_backend"]
    stream = cast(BinaryIO, upload.stream)
    stored_location = storage.store_file(
        stream,
        filename,
        upload.mimetype or "application/octet-stream",
    )
    metadata_document = _build_theme_metadata_document(stored_location)
    metadata_location = _persist_theme_metadata(storage, stored_location, metadata_document)
    return render_template(
        "upload_theme_file.html",
        page_title="Theme analysis uploads",
        page_config=None,
        meta_question=session.get("meta", {}).get("question", "the selected question"),
        errors=errors,
        upload_result={
            "filename": filename,
            "location": stored_location,
            "metadata_location": metadata_location,
        },
    )


@ui_blueprint.get("/confirm")
def confirm() -> ResponseReturnValue:
    """Render a placeholder confirmation page for future actions."""

    return render_template(
        "confirm.html",
        page_title="Confirm selection",
        page_config=None,
    )


@ui_blueprint.get("/login")
def login() -> ResponseReturnValue:
    """Render the login page for session-based authentication."""

    if session.get(SESSION_USER_KEY):
        return redirect(url_for("ui.index"))
    return render_template(
        "login.html",
        page_title="Sign in",
        page_config=None,
        errors=[],
    )


@ui_blueprint.post("/check_login")
def check_login() -> ResponseReturnValue:
    """Validate submitted credentials against users stored in GCS."""

    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""
    if not username or not password:
        return (
            render_template(
                "login.html",
                page_title="Sign in",
                page_config=None,
                errors=["Enter your email address and password."],
            ),
            HTTPStatus.BAD_REQUEST,
        )

    registered_users = _load_registered_users()
    if not _credentials_match(registered_users, username, password):
        return (
            render_template(
                "login.html",
                page_title="Sign in",
                page_config=None,
                errors=["Invalid email address or password."],
            ),
            HTTPStatus.UNAUTHORIZED,
        )

    session[SESSION_USER_KEY] = username
    redirect_target = session.pop(POST_LOGIN_REDIRECT_KEY, url_for("ui.index"))
    return redirect(redirect_target)


def _load_registered_users() -> dict[str, str]:
    """Load login credentials from the configured GCS users JSON file."""

    provider = current_app.config.get("auth_users_provider")
    if callable(provider):
        return cast(dict[str, str], provider())

    storage_backend: StorageBackend = current_app.config["storage_backend"]
    if not isinstance(storage_backend, GCPStorageBackend):
        raise RuntimeError("Login requires a GCP storage backend.")

    settings = current_app.config["settings"]
    users_bucket = settings.bucket_name
    if not users_bucket:
        raise RuntimeError("A bucket name is required to load login users.")

    users_blob = "users.json"
    raw_payload = (
        storage_backend.get_client().bucket(users_bucket).blob(users_blob).download_as_text()
    )
    parsed_payload = json.loads(raw_payload)

    if isinstance(parsed_payload, dict):
        return {
            str(email).strip().lower(): str(stored_password)
            for email, stored_password in parsed_payload.items()
        }

    if isinstance(parsed_payload, list):
        users: dict[str, str] = {}
        for record in parsed_payload:
            if not isinstance(record, dict):
                continue
            username = str(record.get("username") or record.get("email") or "").strip().lower()
            password = str(record.get("password") or "")
            if username and password:
                users[username] = password
        return users
    raise ValueError("users.json must contain a dictionary or list of user records.")


def _credentials_match(registered_users: dict[str, str], username: str, password: str) -> bool:
    """Return True when submitted credentials match the registered user data."""

    stored_password = registered_users.get(username)
    if not stored_password:
        return False

    if stored_password.startswith(("pbkdf2:", "scrypt:", "argon2:")):
        return check_password_hash(stored_password, password)
    return hmac.compare_digest(stored_password, password)


@ui_blueprint.get("/cookies")
def cookies() -> ResponseReturnValue:
    """Render the cookies page that adopts the ONS Design System."""

    return render_template("cookies.html")


@ui_blueprint.get("/accessibility")
def accessibility() -> ResponseReturnValue:
    """Render the accessibility statement page that adopts the ONS Design System."""

    return render_template("accessibility.html")


@ui_blueprint.get("/privacy")
def privacy() -> ResponseReturnValue:
    """Render the privacy and data protection page that adopts the ONS Design System."""

    return render_template("privacy.html")


def _truncate(value: str | None, length: int = 5) -> str:
    """Truncate a string to a specified length, handling None values gracefully."""
    return (value or "")[:length]


def _build_theme_metadata_document(upload_location: str) -> dict[str, Any]:
    """Create the metadata payload that should be persisted alongside the upload."""

    meta = session.setdefault("meta", {})
    survey = meta.get("survey") or DEFAULT_SURVEY
    division = meta.get("division") or DEFAULT_DIVISION
    team = meta.get("team") or DEFAULT_TEAM
    survey_description = meta.get("survey_description") or DEFAULT_SURVEY_DESCRIPTION
    contact = meta.get("contact") or "user@example.com"
    wave = meta.get("wave") or datetime.now().strftime("%d-%m-%Y")
    question = meta.get("question") or "No question provided"

    print(
        f"Building metadata document with "
        f"survey='{survey}', "
        f"division='{division}', "
        f"team='{team}', "
        f"survey_description='{_truncate(survey_description)}', "
        f"contact='{_truncate(contact)}', "
        f"wave='{wave}', "
        f"question='{question}'"
    )
    theme_record = {
        "survey": survey,
        "division": division,
        "team": team,
        "survey_description": survey_description,
        "contact": contact,
        "wave": wave,
        "question": question,
        "supporting_data": upload_location,
    }
    meta.update(
        {
            "survey": survey,
            "division": division,
            "team": team,
            "survey_description": survey_description,
            "contact": contact,
            "wave": wave,
            "theme_record": theme_record,
        }
    )
    session.modified = True
    return {"theme_record": theme_record}


def _persist_theme_metadata(
    storage_backend: StorageBackend, upload_location: str, metadata_document: dict[str, Any]
) -> str:
    """Persist the YAML metadata file alongside the uploaded CSV."""

    yaml_payload = yaml.safe_dump(metadata_document, sort_keys=False)
    if upload_location.startswith("gs://"):
        if not isinstance(storage_backend, GCPStorageBackend):  # pragma: no cover - guard clause
            msg = "GCS upload location requires a GCP storage backend"
            raise RuntimeError(msg)
        return _store_metadata_in_gcs(storage_backend, upload_location, yaml_payload)
    return _store_metadata_locally(upload_location, yaml_payload)


def _store_metadata_locally(upload_location: str, yaml_payload: str) -> str:
    """Write the YAML sidecar file beside the uploaded CSV on disk."""

    csv_path = Path(upload_location)
    if csv_path.suffix:
        yaml_path = csv_path.with_suffix(".yml")
    else:  # pragma: no cover - CSV uploads should always provide a suffix
        yaml_path = csv_path.with_name(f"{csv_path.name}.yml")
    yaml_path.write_text(yaml_payload, encoding="utf-8")
    return str(yaml_path)


def _store_metadata_in_gcs(
    storage_backend: GCPStorageBackend, upload_location: str, yaml_payload: str
) -> str:
    """Upload the YAML metadata file to the same bucket as the CSV."""

    relative_path = upload_location.removeprefix("gs://")
    bucket_name, blob_name = relative_path.split("/", 1)
    metadata_blob_name = str(PurePosixPath(blob_name).with_suffix(".yml"))
    bucket = storage_backend.get_client().bucket(bucket_name)
    blob = bucket.blob(metadata_blob_name)
    blob.upload_from_string(yaml_payload, content_type="application/x-yaml")
    return f"gs://{bucket_name}/{metadata_blob_name}"
