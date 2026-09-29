"""Tests for the local rotating log file (FIBR-0410). See spec.md."""

from __future__ import annotations

import logging
import os
import stat
import sys
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from finbreak import log_file


@pytest.fixture
def clean_finbreak_logger() -> Iterator[logging.Logger]:
    logger = logging.getLogger("finbreak")
    before = list(logger.handlers)
    level = logger.level
    yield logger
    for handler in set(logger.handlers) - set(before):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(level)


def test_INV1_records_reach_an_owner_only_rotating_file(
    tmp_path, clean_finbreak_logger
):
    path = log_file.install_log_file(tmp_path)

    logging.getLogger("finbreak.somewhere").warning("hello from a test")

    assert path == tmp_path / "finbreak.log"
    assert "hello from a test" in path.read_text(encoding="utf-8")
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    handler = next(
        h for h in clean_finbreak_logger.handlers if isinstance(h, RotatingFileHandler)
    )
    assert handler.maxBytes > 0 and handler.backupCount > 0


def test_INV1_a_rotated_file_is_owner_only_too(tmp_path, clean_finbreak_logger):
    path = log_file.install_log_file(tmp_path)
    handler = next(
        h for h in clean_finbreak_logger.handlers if isinstance(h, RotatingFileHandler)
    )
    handler.doRollover()
    logging.getLogger("finbreak").warning("after the rollover")
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_INV2_installing_twice_adds_one_handler(tmp_path, clean_finbreak_logger):
    log_file.install_log_file(tmp_path)
    log_file.install_log_file(tmp_path)
    files = [
        h for h in clean_finbreak_logger.handlers if isinstance(h, RotatingFileHandler)
    ]
    assert len(files) == 1


def test_INV3_an_unwritable_directory_does_not_stop_the_app(
    tmp_path, clean_finbreak_logger
):
    missing = tmp_path / "not-there" / "deeper"
    assert log_file.install_log_file(missing) is None


def test_INV4_run_installs_the_log_file(
    qapp, monkeypatch, app_run_isolation, clean_finbreak_logger
):
    from finbreak import app as app_mod
    from finbreak import single_instance

    installed: list[Path] = []
    monkeypatch.setattr(
        app_mod, "install_log_file", lambda directory: installed.append(directory)
    )
    monkeypatch.setattr(single_instance, "another_instance_is_running", lambda _n: True)
    assert app_mod.run([]) == 0
    assert len(installed) == 1


def test_INV4_settings_shows_the_log_path(qtbot, paths):
    from conftest import _PW
    from finbreak.paths import data_dir
    from finbreak.services.auth import AuthService
    from finbreak.ui.settings import SettingsDialog

    service = AuthService(*paths)
    service.first_run(bytearray(_PW), "ZAR")
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    assert str(log_file.log_file_path(data_dir())) in dialog._log_path.text()
    service.lock()
