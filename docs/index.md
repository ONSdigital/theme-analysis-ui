# Theme Analysis UI

Theme Analysis UI bootstraps a Flask service that mirrors the ONS Design System so analysts can
upload qualitative artefacts in a familiar interface. The project started from the survey-genie template repo and layers the following building blocks:

- App factory + blueprint structure in `theme_analysis_ui.app` and `theme_analysis_ui.routes`
- Storage abstraction switching between local disk and Google Cloud Storage via environment vars
- Google-style docstrings across modules so MkDocs + mkdocstrings can auto-generate references
- Placeholder login route and modular layout prepared for future verification/auth flows

## Theme metadata YAML

Uploads generate a YAML document stored next to the CSV so analysts can preserve context. The
`theme_record` block contains the following keys:

| Field | Description | Default when unset |
| --- | --- | --- |
| `survey` | Human-readable survey name | `Example Survey` |
| `division` | Owning division | `Example Division` |
| `team` | Delivery team | `Example Team` |
| `survey_description` | Short description of the survey | `Example Survey Description` |
| `contact` | Point of contact for follow ups | `user@example.com` |
| `wave` | Collection date/wave identifier | Current date (`DD-MM-YYYY`) |
| `question` | Prompt captured on the metadata form | `No question provided` |
| `supporting_data` | Absolute or GCS path to the uploaded CSV | Upload path |

Values are pulled from `session['meta']` when available. The resolved values are also written back to
session storage so subsequent requests remain in sync with the YAML that was emitted.

## Developing locally

```bash
poetry install --with dev
make fmt
make lint
make test
make run  # starts flask --app theme_analysis_ui.app:create_app run --debug
```

## Documentation preview

```bash
make docs
```

MkDocs Material renders this overview alongside the API reference assembled from the theme_analysis_ui
package.
