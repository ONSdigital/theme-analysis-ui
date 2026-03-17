"""Application entry points for the Theme Analysis UI package.

The module exposes the Flask application factory and settings helpers so
consumers can integrate the UI within broader automation or deploy it as a
standalone web service.
"""

from __future__ import annotations

from .app import create_app
from .config import Settings, load_settings

__all__ = [
    "create_app",
    "Settings",
    "load_settings",
]
