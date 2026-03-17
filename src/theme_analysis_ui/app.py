"""Flask application factory for the Theme Analysis UI."""

from __future__ import annotations

from pathlib import Path

from flask import Flask
from jinja2 import ChainableUndefined, ChoiceLoader, FileSystemLoader

from .config import Settings, load_settings
from .routes.ui import ui_blueprint
from .storage import StorageBackend, build_storage_backend


def create_app(
    settings: Settings | None = None, storage_backend: StorageBackend | None = None
) -> Flask:
    """Create and configure a Flask application instance.

    Args:
        settings (Settings | None): Optional override for dependency injection.
        storage_backend (StorageBackend | None): Optional storage override to
            simplify unit testing.

    Returns:
        Flask: Configured application ready to run.
    """

    resolved_settings = settings or load_settings()
    app = Flask(__name__, template_folder="app_templates")
    app.jinja_env.undefined = ChainableUndefined
    design_templates = Path(__file__).parent / "templates"
    loaders = []
    if app.jinja_loader is not None:
        loaders.append(app.jinja_loader)
    loaders.append(FileSystemLoader(str(design_templates)))
    app.jinja_loader = ChoiceLoader(loaders)
    app.secret_key = resolved_settings.secret_key

    backend = storage_backend or build_storage_backend(resolved_settings)
    app.config["storage_backend"] = backend
    app.config["settings"] = resolved_settings

    app.register_blueprint(ui_blueprint)

    @app.context_processor
    def inject_settings() -> dict[str, Settings]:
        """Expose settings within all templates for design metadata."""

        return {"settings": resolved_settings}

    return app
