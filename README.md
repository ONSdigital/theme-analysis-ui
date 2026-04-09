# Theme Analysis UI

Theme Analysis UI is a Flask application that wraps the [ONS Design System](https://service-manual.ons.gov.uk/design-system)
to provide a consistent interface for uploading qualitative analysis files.

The service ships with storage abstractions for local disk and Google Cloud Storage so testing can switch behaviour with environment variables rather than code forks.

## Application Workflow

The current application workflow is as follows:

- On load the application routes to '/' but will redirect to '/login' when the user is not authenticated
- The login page requires a valid username and password and will reroute to '/' with successful credentials
- On clicking the 'Start' button the application routes to '/theme_meta', renders theme_meta.html and asks 'What is the question associated with the feedback you are analysing?'
  - On this page the user must answer the question before progression
  - The answer is stored in session state
- On clicking the 'Submit response' button the application routes to '/save_meta', renders upload_theme_file.html and asks the user to 'Choose a file' to upload
  - On this page the user must select a CSV file for upload before progression
- On clicking the 'Upload button'
  - The .csv and a .yaml file are stored in the backend
  - The .csv is the respondent feedback being analysed
  - The .yaml is a metadata file including the question associated with the respondent feedback
  - The '/upload' route is displayed showing the locations of the stored files
  - A button "Confirm choices" is rendered
- On clicking "Confirm choices" the application
  - Routes to a placeholder 'confirm' page
  - Starts the theme analysis logic
  - Reports the workflow job execution id that was started

## Stack

- Python ^3.12 managed via Poetry 2.3.2
- Flask 3.1 with blueprints and app factory
- Storage backends: local filesystem (default) or Google Cloud Storage
- Tooling: Ruff, Black, mypy, Bandit, pytest (+ coverage), pre-commit hooks
- Documentation: MkDocs Material + mkdocstrings sourced from Google-style docstrings

## Quick start

```bash
pyenv local 3.12.x
poetry env use $(pyenv which python)
poetry install --with dev
pre-commit install
make fmt && make lint && make test
```

## Downloading the ONS Design System templates

The ONS Design System templates are not checked into git. Before running the app for the first time
(or whenever you want to refresh to a newer release) download the templates via the helper script:

```bash
./scripts/fetch_ons_templates.sh
```

The script downloads a specific release of the `ONSdigital/design-system` templates and unpacks the
`components/` and `layout/` directories into `src/theme_analysis_ui/templates/` so the Flask views
render ONS-styled components locally (the CSS link in the app points to the same release). The
directory is gitignored; re-run the script after cloning or when switching branches if the templates
are missing. To test another release, export `ONS_RELEASE=<tag>` before running the script.

## Environment Variables

An [example .env file](.env.example) is available in the project root.

The following environment variables can be used to define UI behaviour.

**FLASK_ENV** - defaults to 'development'

**FILE_STORE** - defaults to 'LOCAL', should be set as 'GCP' for cloud deployment

**BUCKET_NAME** - the name of the GCP bucket for staging uploaded files.  Only required when FILE_STORE is set as 'GCP'

**UPLOAD_DIR** - defaults to 'uploads' when running in a local filestore

**FLASK_SECRET_KEY** - must be a secure key in deployment

The following environment variables are used to trigger a workflow to perform theme analysis in a cloud run job.

**PROJECT_ID** - The GCP project name

**WORKFLOW_REGION** - The GCP region where the workflow is defined

**WORKFLOW_NAME** - The workflow name in GCP

**CR_JOB_NAME** - The cloud run job name that the workflow will trigger

**CR_JOB_REGION** - The GCP region where the cloud run job is defined

## Running the application

Use the provided Make target to run the Flask development server:

```bash
make run
```

The command wires `flask --app theme_analysis_ui.app:create_app run --debug` so environment
variables automatically cascade into the app factory. Visit http://127.0.0.1:5000 to reach the
upload form rendered through the ONS Design System layout.

## Running in a container (Docker or Podman)

The repository now includes a production-oriented `Dockerfile` suitable for local container
runtime use and Google Cloud Run deployment. It uses a multi-stage build, installs only runtime
dependencies, runs as a non-root user, and serves the app with Gunicorn on port `8080`.

### Build the image

```bash
docker build -t theme-analysis-ui:local .
```

With Podman:

```bash
podman build -t theme-analysis-ui:local .
```

With Podman and amd build:

```bash
podman build --platform linux/amd64 \
  -t <region>-docker.pkg.dev/<gcp-project-name>/theme-analysis-ui/theme-analysis-ui:<tag> \
  .
```

With Podman push to artifact registry:

```bash
podman push <region>-docker.pkg.dev/<gcp-project-name>/theme-analysis-ui/theme-analysis-ui:<tag>
```

### Run container locally

```bash
export FLASK_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker run --rm -p 8000:8000 \
  -e FILE_STORE=GCP \
  -e FLASK_SECRET_KEY=<INSERT-REAL-SECRET> \
  -e BUCKET_NAME=<GCP-STAGING-BUCKET> \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp-key.json \
  -e GOOGLE_CLOUD_PROJECT=<PROJECT-NAME> \
  -v "<path-to>/application_default_credentials.json:/app/secrets/gcp-key.json:Z" \
  theme-analysis-ui:local
```

With Podman:

```bash
export FLASK_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
podman run --rm -p 8000:8000 \
  -e FILE_STORE=GCP \
  -e FLASK_SECRET_KEY=<INSERT-REAL-SECRET> \
  -e BUCKET_NAME=<GCP-STAGING-BUCKET> \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp-key.json \
  -e GOOGLE_CLOUD_PROJECT=<PROJECT-NAME> \
  -v "<path-to>/application_default_credentials.json:/app/secrets/gcp-key.json:Z" \
  theme-analysis-ui:local
```

When using Docker Desktop alternatives such as Colima, start Colima first (for example
`colima start`) and then run the same `docker build` / `docker run` commands.

Visit http://127.0.0.1:8080 once the container is running.

### Cloud Run notes

- Cloud Run injects `PORT`; the image defaults to `8080` and listens on `0.0.0.0`.
- Prefer `FILE_STORE=GCP` in Cloud Run and set `BUCKET_NAME`.
- For `FILE_STORE=GCP`, ensure Application Default Credentials are available: use a Cloud Run service account with Storage access (recommended) or provide `GOOGLE_APPLICATION_CREDENTIALS` in local container runs.
- Do not commit secrets; inject `FLASK_SECRET_KEY` via Secret Manager or Cloud Run environment
  configuration.

## Rendering with the ONS Design System

- Run `./scripts/fetch_ons_templates.sh` after cloning so `src/theme_analysis_ui/templates/` contains the
  `layout/` and `components/` directories from the downloaded release.
- The Flask app loads templates from `app_templates/` and also registers the downloaded design-system templates
  with Jinja. Application views extend `layout/_template.njk` and pull macros (e.g. `onsUpload`, `onsPanel`,
  `onsButton`) directly from the release so components match other ONS services.
- core.html is extended by the basic pages, this provides pageConfig and common elements like navigation.

## Configuring storage

| Variable | Default | Description |
| --- | --- | --- |
| `FILE_STORE` | `LOCAL` | Select `LOCAL` for filesystem uploads or `GCP` for Cloud Storage. |
| `UPLOAD_DIR` | `uploads/` | Target directory for local uploads; created automatically. |
| `BUCKET_NAME` | _required when FILE_STORE=GCP_ | Bucket that receives uploaded files. |
| `FLASK_SECRET_KEY` | `theme-analysis-ui-dev-secret` | Secret key used for session + flash support. |

When `FILE_STORE=GCP`, the application instantiates a `google.cloud.storage.Client` using the
ambient credentials. Local uploads land inside `uploads/` with a UUID prefixed filename so analysts
can forward the artefacts to downstream tooling.

## Theme metadata YAML

Each upload writes a `*.yml` sidecar beside the CSV so downstream tooling can reason about the
survey context. The payload is wrapped in a `theme_record` root node:

```yaml
theme_record:
  survey: Example Survey
  division: Example Division
  team: Example Team
  survey_description: Example Survey Description
  contact: user@example.com
  wave: 01-01-2026
  question: No question provided
  supporting_data: /abs/path/to/upload.csv
```

Values are sourced from `session["meta"]` if they exist (e.g. collected via forms or API calls);
otherwise the defaults listed above are used. After resolving the values, the session metadata is
updated so subsequent requests (such as retries) see consistent values. This makes it easy to extend
the UI with extra metadata prompts without breaking downstream YAML consumers.

## Tests and quality gates

The standard workflow remains unchanged:

```bash
make fmt
make lint
make test
poetry run pre-commit run --all-files
```

Coverage must stay above 80% and Ruff/Bandit/mypy must pass before opening a PR. All modules,
including tests, follow Google-style docstrings written in British English so the MkDocs reference
remains consistent.
