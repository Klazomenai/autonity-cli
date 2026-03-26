"""Tests for aut auth command group (login, status, logout)."""

import json
import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
import requests
import responses
from click import ClickException
from click.testing import CliRunner
from eth_account import Account

from autonity_cli import config
from autonity_cli.__main__ import aut

AUTH_SERVICE = "https://auth.example.com"
# Deterministic test account: known private key → known address
_TEST_PRIVKEY = "0x" + "ab" * 32
_TEST_ACCOUNT = Account.from_key(_TEST_PRIVKEY)
_TEST_ADDRESS = _TEST_ACCOUNT.address  # checksummed


def _make_token(claims: dict[str, object], secret: str = "test-secret") -> str:
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
def mock_keyfile(tmp_path: Path) -> Path:
    """Encrypted keyfile with known private key for deterministic signing."""
    encrypted = Account.encrypt(_TEST_PRIVKEY, "test-password")
    path = tmp_path / "test-keyfile.json"
    path.write_text(json.dumps(encrypted))
    return path


def _mock_challenge() -> None:
    """Register a successful challenge response."""
    responses.post(
        f"{AUTH_SERVICE}/auth/challenge",
        json={"message": "Sign in with Ethereum...", "nonce": "abc123"},
    )


def _mock_token(token: str = "eyJ-test-jwt") -> None:
    """Register a successful token response."""
    responses.post(
        f"{AUTH_SERVICE}/auth/token",
        json={"parent_token": token, "parent_jti": "jti-1"},
    )


def _login_args(keyfile: Path) -> list[str]:
    """Standard login args with keyfile and auth service."""
    return [
        "auth", "login",
        "--keyfile", str(keyfile),
        "--auth-service", AUTH_SERVICE,
    ]


class TestGetAuthService:
    def test_cli_param_takes_precedence(self) -> None:
        result = config.get_auth_service("https://cli.example.com")
        assert result == "https://cli.example.com"

    def test_env_var_fallback(self) -> None:
        with patch.dict("os.environ", {"AUT_AUTH_SERVICE": "https://env.example.com"}):
            result = config.get_auth_service()
        assert result == "https://env.example.com"

    def test_config_file_fallback(
        self, runner: CliRunner, autrc: Callable[..., Path]
    ) -> None:
        autrc(auth_service="https://file.example.com")
        result = config.get_auth_service()
        assert result == "https://file.example.com"

    def test_raises_when_none_configured(self) -> None:
        with pytest.raises(ClickException, match="no auth service configured"):
            config.get_auth_service()

    def test_cli_overrides_env(self) -> None:
        with patch.dict("os.environ", {"AUT_AUTH_SERVICE": "https://env.example.com"}):
            result = config.get_auth_service("https://cli.example.com")
        assert result == "https://cli.example.com"

    def test_env_overrides_file(
        self, runner: CliRunner, autrc: Callable[..., Path]
    ) -> None:
        autrc(auth_service="https://file.example.com")
        with patch.dict("os.environ", {"AUT_AUTH_SERVICE": "https://env.example.com"}):
            result = config.get_auth_service()
        assert result == "https://env.example.com"


class TestAuthLogin:
    # --- Happy path ---

    @responses.activate
    def test_login_success(self, runner: CliRunner, mock_keyfile: Path) -> None:
        _mock_challenge()
        _mock_token()
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code == 0
        assert "logged in as" in result.output

    @responses.activate
    def test_login_success_shows_address(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        _mock_token()
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code == 0
        assert _TEST_ADDRESS in result.output

    @responses.activate
    def test_login_success_shows_path(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        _mock_token()
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code == 0
        assert "token stored in" in result.output
        assert ".autrc" in result.output

    @responses.activate
    def test_login_token_stored_in_config(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        _mock_token("stored-jwt-value")
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code == 0
        content = Path(".autrc").read_text()
        assert "stored-jwt-value" in content

    # --- Auth service resolution ---

    @responses.activate
    def test_login_auth_service_from_cli(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        _mock_token()
        result = runner.invoke(
            aut,
            ["auth", "login",
             "--keyfile", str(mock_keyfile),
             "--auth-service", AUTH_SERVICE],
            input="test-password\n",
        )
        assert result.exit_code == 0
        assert responses.calls[0].request.url == f"{AUTH_SERVICE}/auth/challenge"

    @responses.activate
    def test_login_auth_service_from_env(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        _mock_token()
        with patch.dict("os.environ", {"AUT_AUTH_SERVICE": AUTH_SERVICE}):
            result = runner.invoke(
                aut,
                ["auth", "login", "--keyfile", str(mock_keyfile)],
                input="test-password\n",
            )
        assert result.exit_code == 0

    @responses.activate
    def test_login_auth_service_from_config(
        self, runner: CliRunner, mock_keyfile: Path, autrc: Callable[..., Path]
    ) -> None:
        autrc(auth_service=AUTH_SERVICE)
        _mock_challenge()
        _mock_token()
        result = runner.invoke(
            aut,
            ["auth", "login", "--keyfile", str(mock_keyfile)],
            input="test-password\n",
        )
        assert result.exit_code == 0

    # --- Error: no auth service ---

    def test_login_no_auth_service(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        result = runner.invoke(
            aut,
            ["auth", "login", "--keyfile", str(mock_keyfile)],
            input="test-password\n",
        )
        assert result.exit_code != 0
        assert "no auth service configured" in result.output

    # --- Error: challenge endpoint ---

    @responses.activate
    def test_login_challenge_connection_error(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        responses.post(
            f"{AUTH_SERVICE}/auth/challenge",
            body=requests.ConnectionError("refused"),
        )
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code != 0
        assert "cannot reach auth service" in result.output

    @responses.activate
    def test_login_challenge_500(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        responses.post(f"{AUTH_SERVICE}/auth/challenge", status=500, body="internal error")
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code != 0
        assert "challenge failed: 500" in result.output

    @responses.activate
    def test_login_challenge_404(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        responses.post(f"{AUTH_SERVICE}/auth/challenge", status=404, body="not found")
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code != 0
        assert "challenge failed: 404" in result.output

    @responses.activate
    def test_login_challenge_timeout(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        responses.post(
            f"{AUTH_SERVICE}/auth/challenge",
            body=requests.Timeout("timed out"),
        )
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code != 0
        assert "timed out" in result.output

    @responses.activate
    def test_login_challenge_missing_message(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        responses.post(
            f"{AUTH_SERVICE}/auth/challenge",
            json={"nonce": "abc123"},  # no "message" field
        )
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code != 0
        assert "missing 'message' field" in result.output

    # --- Error: token endpoint ---

    @responses.activate
    def test_login_token_connection_error(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        responses.post(
            f"{AUTH_SERVICE}/auth/token",
            body=requests.ConnectionError("refused"),
        )
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code != 0
        assert "cannot reach auth service" in result.output

    @responses.activate
    def test_login_token_401(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        responses.post(f"{AUTH_SERVICE}/auth/token", status=401, body="invalid signature")
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code != 0
        assert "authentication failed: 401" in result.output

    @responses.activate
    def test_login_token_403(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        responses.post(f"{AUTH_SERVICE}/auth/token", status=403, body="access denied")
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code != 0
        assert "authentication failed: 403" in result.output

    @responses.activate
    def test_login_token_502(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        responses.post(f"{AUTH_SERVICE}/auth/token", status=502, body="bad gateway")
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code != 0
        assert "authentication failed: 502" in result.output

    @responses.activate
    def test_login_token_missing_both_fields(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        responses.post(
            f"{AUTH_SERVICE}/auth/token",
            json={"parent_jti": "jti-1"},  # no parent_token or token field
        )
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code != 0
        assert "missing 'parent_token' or 'token' field" in result.output

    @responses.activate
    def test_login_legacy_token_field(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        """Auth service returns legacy {token: ...} instead of {parent_token: ...}."""
        _mock_challenge()
        responses.post(
            f"{AUTH_SERVICE}/auth/token",
            json={"token": "legacy-jwt-value", "token_id": "jti-1"},
        )
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code == 0
        content = Path(".autrc").read_text()
        assert "legacy-jwt-value" in content

    # --- Edge cases ---

    @responses.activate
    def test_login_overwrites_existing_token(
        self, runner: CliRunner, mock_keyfile: Path, autrc: Callable[..., Path]
    ) -> None:
        autrc(auth_token="old-jwt")
        _mock_challenge()
        _mock_token("new-jwt")
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code == 0
        content = Path(".autrc").read_text()
        assert "new-jwt" in content
        assert "old-jwt" not in content

    @responses.activate
    def test_login_signature_has_0x_prefix(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        _mock_token()
        result = runner.invoke(aut, _login_args(mock_keyfile), input="test-password\n")
        assert result.exit_code == 0
        # Check the token request body for 0x-prefixed signature
        token_request = json.loads(responses.calls[1].request.body)
        assert token_request["signature"].startswith("0x")

    @responses.activate
    def test_login_strips_trailing_slash(
        self, runner: CliRunner, mock_keyfile: Path
    ) -> None:
        _mock_challenge()
        _mock_token()
        result = runner.invoke(
            aut,
            ["auth", "login",
             "--keyfile", str(mock_keyfile),
             "--auth-service", AUTH_SERVICE + "/"],
            input="test-password\n",
        )
        assert result.exit_code == 0
        # URL should not have double slash
        assert "//" not in responses.calls[0].request.url.split("://")[1]


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
