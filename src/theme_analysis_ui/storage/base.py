"""Storage backend protocol shared by all upload destinations."""

from __future__ import annotations

from typing import BinaryIO, Protocol


class StorageBackend(Protocol):
    """Describe the interface required by upload storage backends."""

    def store_file(self, source: BinaryIO, filename: str, content_type: str) -> str:
        """Persist a file-like object and return a human readable location.

        Args:
            source (BinaryIO): Stream pointing at the data to persist.
            filename (str): User supplied filename used to build the target name.
            content_type (str): MIME type reported by the browser.

        Returns:
            str: A URI or filesystem path describing where the file landed.
        """
