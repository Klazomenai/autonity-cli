"""Tests for auth_token configuration and HTTP header injection."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from web3 import HTTPProvider, IPCProvider, LegacyWebSocketProvider

from autonity_cli import config
from autonity_cli.utils import web3_provider_for_endpoint


class TestGetAuthToken:
    """Test auth token precedence: CLI > env > config file."""

    def test_no_token_returns_none(self) -> None:
        assert config.get_auth_token() is None

    def test_cli_token(self) -> None:
        config.set_auth_token_from_cli("cli-token")
        assert config.get_auth_token() == "cli-token"

    def test_env_token(self) -> None:
        with patch.dict("os.environ", {"AUT_AUTH_TOKEN": "env-token"}):
            assert config.get_auth_token() == "env-token"

    def test_config_file_token(self, autrc: Callable[..., Path]) -> None:
        autrc(auth_token="file-token")
        assert config.get_auth_token() == "file-token"

    def test_cli_beats_env(self) -> None:
        config.set_auth_token_from_cli("cli-token")
        with patch.dict("os.environ", {"AUT_AUTH_TOKEN": "env-token"}):
            assert config.get_auth_token() == "cli-token"

    def test_cli_beats_config_file(self, autrc: Callable[..., Path]) -> None:
        autrc(auth_token="file-token")
        config.set_auth_token_from_cli("cli-token")
        assert config.get_auth_token() == "cli-token"

    def test_env_beats_config_file(self, autrc: Callable[..., Path]) -> None:
        autrc(auth_token="file-token")
        with patch.dict("os.environ", {"AUT_AUTH_TOKEN": "env-token"}):
            assert config.get_auth_token() == "env-token"

    def test_empty_string_returns_none(self) -> None:
        config.set_auth_token_from_cli("")
        assert config.get_auth_token() is None

    def test_whitespace_only_returns_none(self) -> None:
        config.set_auth_token_from_cli("   ")
        assert config.get_auth_token() is None

    def test_whitespace_stripped(self) -> None:
        config.set_auth_token_from_cli("  my-token  ")
        assert config.get_auth_token() == "my-token"

    def test_empty_env_falls_through_to_file(self, autrc: Callable[..., Path]) -> None:
        """Empty/whitespace env var should fall through to config file."""
        autrc(auth_token="file-token")
        with patch.dict("os.environ", {"AUT_AUTH_TOKEN": "  "}):
            assert config.get_auth_token() == "file-token"

    def test_empty_cli_falls_through_to_env(self) -> None:
        """Empty CLI value should fall through to env var."""
        config.set_auth_token_from_cli("  ")
        with patch.dict("os.environ", {"AUT_AUTH_TOKEN": "env-token"}):
            assert config.get_auth_token() == "env-token"


class TestProviderHeaderInjection:
    """Test Bearer header injection in web3_provider_for_endpoint."""

    def test_http_no_token(self) -> None:
        provider = web3_provider_for_endpoint("https://rpc.example.com")
        assert isinstance(provider, HTTPProvider)

    def test_http_with_token(self) -> None:
        config.set_auth_token_from_cli("my-jwt")
        provider = web3_provider_for_endpoint("https://rpc.example.com")
        assert isinstance(provider, HTTPProvider)
        headers = provider._request_kwargs["headers"]  # type: ignore[attr-defined]
        assert headers["Authorization"] == "Bearer my-jwt"

    def test_plain_http_with_token_warns(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plain HTTP + token should warn but still inject header."""
        from autonity_cli.logging import enable_logging

        enable_logging()
        config.set_auth_token_from_cli("my-jwt")
        provider = web3_provider_for_endpoint("http://localhost:8545")
        assert isinstance(provider, HTTPProvider)
        headers = provider._request_kwargs["headers"]  # type: ignore[attr-defined]
        assert headers["Authorization"] == "Bearer my-jwt"
        captured = capsys.readouterr()
        assert "sending auth token over plain HTTP" in captured.err

    def test_https_no_http_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        """HTTPS should not trigger plain HTTP warning."""
        from autonity_cli.logging import enable_logging

        enable_logging()
        config.set_auth_token_from_cli("my-jwt")
        provider = web3_provider_for_endpoint("https://rpc.example.com")
        assert isinstance(provider, HTTPProvider)
        captured = capsys.readouterr()
        assert "sending auth token over plain HTTP" not in captured.err

    def test_ws_with_token_warns(self, capsys: pytest.CaptureFixture[str]) -> None:
        config.set_auth_token_from_cli("my-jwt")
        # Enable logging so warning is emitted
        from autonity_cli.logging import enable_logging

        enable_logging()
        provider = web3_provider_for_endpoint("ws://localhost:8546")
        assert isinstance(provider, LegacyWebSocketProvider)
        captured = capsys.readouterr()
        assert "WebSocket provider does not support custom headers" in captured.err

    def test_ws_no_token_no_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        provider = web3_provider_for_endpoint("ws://localhost:8546")
        assert isinstance(provider, LegacyWebSocketProvider)
        captured = capsys.readouterr()
        assert "WebSocket" not in captured.err

    def test_ipc_with_token_silent(self, capsys: pytest.CaptureFixture[str]) -> None:
        """IPC + token should silently ignore the token, no warnings."""
        from autonity_cli.logging import enable_logging

        enable_logging()
        config.set_auth_token_from_cli("my-jwt")
        provider = web3_provider_for_endpoint("/tmp/node.ipc")
        assert isinstance(provider, IPCProvider)
        captured = capsys.readouterr()
        assert "WARNING" not in captured.err

    def test_invalid_endpoint_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot determine provider"):
            web3_provider_for_endpoint("ftp://bad.endpoint")
