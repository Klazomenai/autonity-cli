"""Tests for aut auth command group (login, status, logout)."""

import json
import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import jwt
from click.testing import CliRunner

from autonity_cli.__main__ import aut


def _make_token(claims: dict[str, object], secret: str = "test-secret") -> str:
    return jwt.encode(claims, secret, algorithm="HS256")


class TestAuthLogin:
    def test_login_not_implemented(self, runner: CliRunner) -> None:
        result = runner.invoke(aut, ["auth", "login"])
        assert result.exit_code != 0
        assert "not yet implemented" in result.output


class TestAuthStatus:
    def test_status_no_token(self, runner: CliRunner) -> None:
        result = runner.invoke(aut, ["auth", "status"])
        assert result.exit_code != 0
        assert "no auth token configured" in result.output
        assert "config file" in result.output

    def test_status_valid_token(self, runner: CliRunner) -> None:
        token = _make_token({"sub": "0xABC", "exp": int(time.time()) + 7200})
        result = runner.invoke(aut, ["--auth-token", token, "auth", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["expired"] is False
        assert "claims" in data
        assert data["claims"]["sub"] == "0xABC"

    def test_status_expired_token(self, runner: CliRunner) -> None:
        token = _make_token({"sub": "0xABC", "exp": int(time.time()) - 3600})
        result = runner.invoke(aut, ["--auth-token", token, "auth", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["expired"] is True
        assert "EXPIRED" in data["expires_in"]

    def test_status_no_exp_claim(self, runner: CliRunner) -> None:
        token = _make_token({"sub": "0xABC", "role": "admin"})
        result = runner.invoke(aut, ["--auth-token", token, "auth", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "expired" not in data
        assert "expires_in" not in data
        assert data["claims"]["sub"] == "0xABC"

    def test_status_invalid_token(self, runner: CliRunner) -> None:
        result = runner.invoke(aut, ["--auth-token", "not.a.jwt", "auth", "status"])
        assert result.exit_code != 0
        assert "failed to decode" in result.output

    def test_status_non_hs256_algorithm(self, runner: CliRunner) -> None:
        token = jwt.encode(
            {"sub": "0xABC", "exp": int(time.time()) + 600},
            "a]long-enough-secret-for-hs512!!",
            algorithm="HS512",
        )
        result = runner.invoke(aut, ["--auth-token", token, "auth", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["claims"]["sub"] == "0xABC"

    def test_status_unparseable_exp(self, runner: CliRunner) -> None:
        token = _make_token({"sub": "0xABC", "exp": "not-a-number"})
        result = runner.invoke(aut, ["--auth-token", token, "auth", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "expired" not in data
        assert "expires_in" not in data
        assert data["claims"]["sub"] == "0xABC"

    def test_status_from_env(self, runner: CliRunner) -> None:
        token = _make_token({"sub": "env-test", "exp": int(time.time()) + 600})
        with patch.dict("os.environ", {"AUT_AUTH_TOKEN": token}):
            result = runner.invoke(aut, ["auth", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["claims"]["sub"] == "env-test"

    def test_status_from_config_file(
        self, runner: CliRunner, autrc: Callable[..., Path]
    ) -> None:
        token = _make_token({"sub": "file-test", "exp": int(time.time()) + 600})
        autrc(auth_token=token)
        result = runner.invoke(aut, ["auth", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["claims"]["sub"] == "file-test"


class TestAuthLogout:
    def test_logout_removes_token(
        self, runner: CliRunner, autrc: Callable[..., Path]
    ) -> None:
        autrc(auth_token="some-jwt")
        result = runner.invoke(aut, ["auth", "logout"])
        assert result.exit_code == 0
        assert "auth_token removed" in result.output
        # Verify token is gone from file
        content = Path(".autrc").read_text()
        assert "auth_token" not in content

    def test_logout_preserves_other_config(
        self, runner: CliRunner, autrc: Callable[..., Path]
    ) -> None:
        autrc(rpc_endpoint="https://rpc.example.com", auth_token="some-jwt")
        result = runner.invoke(aut, ["auth", "logout"])
        assert result.exit_code == 0
        content = Path(".autrc").read_text()
        assert "auth_token" not in content
        assert "rpc_endpoint" in content
        assert "https://rpc.example.com" in content

    def test_logout_no_config_file(self, runner: CliRunner) -> None:
        result = runner.invoke(aut, ["auth", "logout"])
        assert result.exit_code == 0
        assert "nothing to do" in result.output

    def test_logout_no_token_in_config(
        self, runner: CliRunner, autrc: Callable[..., Path]
    ) -> None:
        autrc(rpc_endpoint="https://rpc.example.com")
        result = runner.invoke(aut, ["auth", "logout"])
        assert result.exit_code == 0
        assert "nothing to do" in result.output
