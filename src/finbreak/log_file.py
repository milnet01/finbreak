"""The local rotating log file design.md § Observability promises (FIBR-0410).

No handler was installed anywhere, so every log call went to stderr through
``logging.lastResort`` or nowhere, and the log path Settings was meant to show
did not exist. What the log may contain is security-model INV-9's: operations
and errors, never transaction contents, passwords, keys or decrypted data.

Qt-free on purpose: the caller hands in the data directory.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILENAME = "finbreak.log"
# Small: the log is for support, and a local finance app has no reason to keep
# more than recent history on disk.
_MAX_BYTES = 1024 * 1024
_BACKUPS = 3
_LOGGER = "finbreak"


def log_file_path(directory: Path) -> Path:
    """Where the log lives inside the data directory ``directory``."""
    return directory / LOG_FILENAME


class _OwnerOnlyRotatingFileHandler(RotatingFileHandler):
    """A ``RotatingFileHandler`` whose file is created owner-only (0600).

    The stock handler opens with ``open()``, so the file, and every fresh one
    after a rollover, takes the process umask and is commonly world-readable.
    ``O_NOFOLLOW`` refuses a symlink planted at the path.
    """

    def _open(self):  # type: ignore[no-untyped-def]
        fd = os.open(
            self.baseFilename,
            os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        return os.fdopen(fd, self.mode, encoding=self.encoding, errors=self.errors)


def install_log_file(directory: Path) -> Path | None:
    """Send the ``finbreak`` logger's records to a rotating file in ``directory``.

    Returns the file's path, or ``None`` when it cannot be opened: logging must
    never stop the app from starting. Installing twice adds one handler.
    """
    path = log_file_path(directory)
    logger = logging.getLogger(_LOGGER)
    for handler in logger.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename) == path.resolve()
        ):
            return path
    try:
        handler = _OwnerOnlyRotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
        )
    except OSError:
        return None
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    if logger.level == logging.NOTSET or logger.level > logging.INFO:
        logger.setLevel(logging.INFO)
    return path
