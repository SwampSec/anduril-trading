import pathlib
import subprocess

import pytest

from broker.logging_utils import log_account_status


def _is_gitignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", path],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


@pytest.mark.unit
def test_no_dotenv_committed():
    assert not pathlib.Path(".env").exists() or _is_gitignored(".env"), (
        ".env must be gitignored and never committed"
    )


@pytest.mark.unit
def test_account_numbers_masked_in_logs(caplog, fake_broker):
    caplog.set_level("INFO")
    log_account_status(fake_broker)
    assert "DU1234567" not in caplog.text
