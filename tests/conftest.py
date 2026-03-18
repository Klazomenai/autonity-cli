"""Shared test fixtures."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from autonity_cli import config
from autonity_cli import config_file
from autonity_cli import logging as cli_logging


def _clear_module_state() -> None:
    """Reset all module-level globals to their defaults."""
    config.set_auth_token_from_cli(None)
    config_file.config_file_cached = False
    config_file.config_file_data = config_file.ConfigFile({})
    config_file.config_file_dir = "."
    cli_logging.logging_enabled = False


@pytest.fixture(autouse=True)
def _reset_module_state(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[None]:
    """Reset module-level state and isolate from host environment."""
    _clear_module_state()
    monkeypatch.delenv(config.AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    yield
    _clear_module_state()


@pytest.fixture
def runner() -> Iterator[CliRunner]:
    """CliRunner with isolated filesystem."""
    runner_ = CliRunner()
    with runner_.isolated_filesystem():
        yield runner_


@pytest.fixture
def autrc(runner: CliRunner) -> Callable[..., Path]:
    """Create a temporary .autrc file. Returns factory function."""

    def _make_autrc(**fields: str) -> Path:
        lines = ["[aut]\n"]
        for k, v in fields.items():
            lines.append(f"{k} = {v}\n")
        path = Path(".autrc")
        path.write_text("".join(lines))
        return path

    return _make_autrc
