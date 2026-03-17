"""Implementation of the local filesystem storage backend."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import copyfileobj
from typing import BinaryIO
from uuid import uuid4

from werkzeug.utils import secure_filename

from .base import StorageBackend


@dataclass
class LocalStorageBackend(StorageBackend):
    """Persist uploaded files inside a project-local directory."""

    root: Path

    def store_file(self, source: BinaryIO, filename: str, content_type: str) -> str:  # noqa: D401
        """Persist the uploaded file to disk and return the absolute path."""

        safe_name = secure_filename(filename) or "upload.bin"
        target_name = f"{uuid4().hex}_{safe_name}"
        target_path = self.root / target_name
        self.root.mkdir(parents=True, exist_ok=True)
        source.seek(0)
        with target_path.open("wb") as handle:
            copyfileobj(source, handle)
        return str(target_path)
