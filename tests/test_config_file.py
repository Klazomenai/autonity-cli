"""Tests for config_file.set_config_value()."""

from pathlib import Path

from autonity_cli import config_file
from autonity_cli.config_file import set_config_value


class TestSetConfigValue:
    def test_create_new_file(self, tmp_path: Path) -> None:
        """Creates .autrc with [aut] section when none exists."""
        import os

        os.chdir(tmp_path)
        path = set_config_value("auth_token", "test-jwt")
        content = Path(path).read_text()
        assert "[aut]" in content
        assert "auth_token = test-jwt" in content

    def test_add_to_existing(self, tmp_path: Path) -> None:
        """Adds a new key to an existing .autrc."""
        import os

        os.chdir(tmp_path)
        Path(".autrc").write_text("[aut]\nrpc_endpoint = https://rpc.example.com\n")
        set_config_value("auth_token", "new-jwt")
        content = Path(".autrc").read_text()
        assert "auth_token = new-jwt" in content
        assert "rpc_endpoint = https://rpc.example.com" in content

    def test_overwrite_existing_key(self, tmp_path: Path) -> None:
        """Updates value of an existing key."""
        import os

        os.chdir(tmp_path)
        Path(".autrc").write_text("[aut]\nauth_token = old-jwt\n")
        set_config_value("auth_token", "new-jwt")
        content = Path(".autrc").read_text()
        assert "new-jwt" in content
        assert "old-jwt" not in content

    def test_preserve_other_keys(self, tmp_path: Path) -> None:
        """Other keys in [aut] section are untouched."""
        import os

        os.chdir(tmp_path)
        Path(".autrc").write_text(
            "[aut]\nrpc_endpoint = https://rpc.example.com\nkeystore = /keys\n"
        )
        set_config_value("auth_token", "jwt-value")
        content = Path(".autrc").read_text()
        assert "rpc_endpoint = https://rpc.example.com" in content
        assert "keystore = /keys" in content
        assert "auth_token = jwt-value" in content

    def test_preserve_other_sections(self, tmp_path: Path) -> None:
        """Non-[aut] sections are preserved."""
        import os

        os.chdir(tmp_path)
        Path(".autrc").write_text("[aut]\nfoo = bar\n\n[other]\nkey = val\n")
        set_config_value("auth_token", "jwt")
        content = Path(".autrc").read_text()
        assert "[other]" in content
        assert "key = val" in content

    def test_invalidates_cache(self, tmp_path: Path) -> None:
        """config_file_cached is False after write."""
        import os

        os.chdir(tmp_path)
        config_file.config_file_cached = True
        set_config_value("auth_token", "jwt")
        assert config_file.config_file_cached is False

    def test_returns_path(self, tmp_path: Path) -> None:
        """Return value is the config file path."""
        import os

        os.chdir(tmp_path)
        path = set_config_value("auth_token", "jwt")
        assert path.endswith(".autrc")
        assert Path(path).exists()

    def test_creates_section_if_missing(self, tmp_path: Path) -> None:
        """File exists but has no [aut] section."""
        import os

        os.chdir(tmp_path)
        Path(".autrc").write_text("[other]\nkey = val\n")
        set_config_value("auth_token", "jwt")
        content = Path(".autrc").read_text()
        assert "[aut]" in content
        assert "auth_token = jwt" in content
        assert "[other]" in content
