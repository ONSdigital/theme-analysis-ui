"""User facing routes for uploads and authentication flows."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import tempfile
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
from survey_assist_pii.reporting.json_report import build_json_report
from survey_assist_pii.services.pii_service import validate_csv_file
from werkzeug.datastructures import FileStorage
from werkzeug.security import check_password_hash
import yaml

from theme_analysis_ui.utils.workflow_utils import get_workflow_config, trigger_workflow

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
    if request.endpoint in {
        "ui.login",
        "ui.check_login",
        "static",
    }:
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
    try:
        validation_result = _validate_uploaded_csv(upload)
    except (ValueError, OSError) as exc:
        return (
            render_template(
                "upload_theme_file.html",
                page_title="Theme analysis uploads",
                page_config=None,
                meta_question=session.get("meta", {}).get("question", "the selected question"),
                errors=[str(exc)],
                upload_result=None,
            ),
            HTTPStatus.BAD_REQUEST,
        )
    upload.stream.seek(0)
    filename = upload.filename
    storage: StorageBackend = current_app.config["storage_backend"]
    stream = cast(BinaryIO, upload.stream)
    stored_location = storage.store_file(
        stream,
        filename,
        upload.mimetype or "application/octet-stream",
    )
    if validation_result["has_findings"]:
        report_filename = f"{Path(filename).stem}_pii_report.json"

        report_location = storage.store_file(
            BytesIO(validation_result["report_bytes"]),
            report_filename,
            "application/json",
        )

        session["pending_upload"] = {
            "filename": filename,
            "csv_file": stored_location,
        }
        session["flagged_rows"] = validation_result["flagged_rows"]
        session["pii_report_location"] = report_location
        session.modified = True

        return redirect(url_for("ui.review_responses"))

    metadata_document = _build_theme_metadata_document(stored_location)
    metadata_location = _persist_theme_metadata(storage, stored_location, metadata_document)

    # Save the upload information
    session["upload"] = {
        "filename": filename,
        "csv_file": stored_location,
        "meta_file": metadata_location,
    }
    session.pop("pending_upload", None)
    session.pop("flagged_rows", None)

    session.modified = True  # Ensure session is saved even if only modified in-place

    return redirect(url_for("ui.upload_complete"))


@ui_blueprint.get("/confirm")
def confirm() -> ResponseReturnValue:
    """Render a placeholder confirmation page for future actions."""

    settings = current_app.config["settings"]
    staging_bucket = settings.bucket_name

    # Get upload information from the session
    upload_info = session.get("upload", {})
    csv_object = upload_info.get("csv_file")
    metadata_object = upload_info.get("meta_file")
    question = session.get("meta", {}).get("question", "No question provided")
    output_prefix = f"outputs/{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    project_id, region, workflow_name, cr_job_name, cr_job_region = get_workflow_config()

    # Trigger theme analysis workflow after upload
    execution_name = trigger_workflow(
        project_id=project_id,
        region=region,
        workflow_name=workflow_name,
        staging_bucket=staging_bucket,
        csv_object=csv_object,
        metadata_object=metadata_object,
        question=question,
        output_prefix=output_prefix,
        job_name=cr_job_name,
        job_region=cr_job_region,
    )

    return render_template(
        "confirm.html",
        page_title="Confirm selection",
        page_config=None,
        execution_name=execution_name,
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
    """Load login credentials from the configured users JSON file."""

    provider = current_app.config.get("auth_users_provider")
    if callable(provider):
        return cast(dict[str, str], provider())

    storage_backend: StorageBackend = current_app.config["storage_backend"]

    if isinstance(storage_backend, GCPStorageBackend):
        settings = current_app.config["settings"]
        users_bucket = settings.bucket_name
        if not users_bucket:
            raise RuntimeError("A bucket name is required to load login users.")

        raw_payload = (
            storage_backend.get_client().bucket(users_bucket).blob("users.json").download_as_text()
        )
    else:
        users_file = Path(current_app.root_path).parent.parent / "users.json"
        if not users_file.exists():
            raise RuntimeError(f"Local login file not found: {users_file}")
        raw_payload = users_file.read_text(encoding="utf-8")

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

    print("Error: stored password does not appear to be a valid hash.")
    return False


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


@ui_blueprint.route("/review_responses", methods=["GET", "POST"])
def review_responses() -> ResponseReturnValue:
    flagged_rows = session.get("flagged_rows", [])
    pending_upload = session.get("pending_upload")
    errors: list[str] = []

    if not pending_upload:
        return redirect(url_for("ui.theme_meta"))

    if request.method == "GET":
        return render_template(
            "review_responses.html",
            page_title="Review responses",
            flagged_rows=flagged_rows,
            errors=errors,
        )

    ignore_warning = request.form.get("ignore_disclosure_warning")
    if not ignore_warning:
        return (
            render_template(
                "review_responses.html",
                page_title="Review responses",
                flagged_rows=flagged_rows,
                errors=["Select 'These are ok to ignore' before continuing."],
            ),
            HTTPStatus.BAD_REQUEST,
        )

    storage: StorageBackend = current_app.config["storage_backend"]
    stored_location = pending_upload["csv_file"]

    metadata_document = _build_theme_metadata_document(stored_location)
    metadata_location = _persist_theme_metadata(storage, stored_location, metadata_document)

    session["upload"] = {
        "filename": pending_upload["filename"],
        "csv_file": stored_location,
        "meta_file": metadata_location,
    }
    session.pop("pending_upload", None)
    session.pop("flagged_rows", None)
    session.modified = True

    return render_template(
        "upload_theme_file.html",
        page_title="Theme analysis uploads",
        page_config=None,
        meta_question=session.get("meta", {}).get("question", "the selected question"),
        errors=[],
        upload_result={
            "filename": pending_upload["filename"],
            "location": stored_location,
            "metadata_location": metadata_location,
        },
    )


@ui_blueprint.get("/cancel")
def cancel() -> ResponseReturnValue:
    pii_report_location = session.get("pii_report_location")
    flagged_rows = session.get("flagged_rows", [])

    return render_template(
        "cancel.html",
        page_title="Upload cancelled",
        pii_report_location=pii_report_location,
        flagged_rows=flagged_rows,
    )


@ui_blueprint.post("/start_analysis")
def start_analysis() -> ResponseReturnValue:
    settings = current_app.config["settings"]
    staging_bucket = settings.bucket_name

    upload_info = session.get("upload", {})
    csv_object = upload_info.get("csv_file")
    metadata_object = upload_info.get("meta_file")
    question = session.get("meta", {}).get("question", "No question provided")

    output_prefix = f"outputs/{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    project_id, region, workflow_name, cr_job_name, cr_job_region = get_workflow_config()

    execution_name = trigger_workflow(
        project_id=project_id,
        region=region,
        workflow_name=workflow_name,
        staging_bucket=staging_bucket,
        csv_object=csv_object,
        metadata_object=metadata_object,
        question=question,
        output_prefix=output_prefix,
        job_name=cr_job_name,
        job_region=cr_job_region,
    )

    return render_template(
        "confirm.html",
        page_title="Analysis started",
        execution_name=execution_name,
    )


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


def _validate_uploaded_csv(upload: FileStorage) -> dict[str, Any]:
    """Validate the uploaded CSV file for PII and return any flagged rows."""
    filename = upload.filename or "upload.csv"
    suffix = Path(filename).suffix or ".csv"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        upload.save(tmp.name)
        temp_path = Path(tmp.name)

    try:
        result = validate_csv_file(
            input_file=temp_path,
            delimiter="|",
        )

        flagged_rows = [
            {
                "row_number": report.row_number,
                "response_text": report.comment,
            }
            for report in result.reports
        ]

        json_report = build_json_report(result)
        report_json = json.dumps(asdict(json_report), indent=2)

        return {
            "has_findings": result.has_findings,
            "flagged_rows": flagged_rows,
            "report_bytes": report_json.encode("utf-8"),
        }

    finally:
        temp_path.unlink(missing_ok=True)
