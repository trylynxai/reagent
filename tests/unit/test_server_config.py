"""Unit tests for Config mode/server fields and ServerConfig validation."""

import pytest

from reagent.core.config import Config, ServerConfig
from reagent.core.exceptions import ConfigError


class TestConfigModeDefaults:
    """Tests for default mode and server configuration."""

    def test_default_mode_is_local(self):
        """Default mode is 'local'."""
        config = Config()
        assert config.mode == "local"

    def test_default_server_config_values(self):
        """Default ServerConfig has expected defaults."""
        config = Config()
        assert config.server.url is None
        assert config.server.api_key is None
        assert config.server.batch_size == 50
        assert config.server.flush_interval_ms == 2000
        assert config.server.timeout_seconds == 10.0
        assert config.server.retry_max == 3
        assert config.server.fallback_to_local is True


class TestConfigLoadWithOverrides:
    """Tests for Config.load() with runtime_overrides."""

    def test_load_sets_mode_to_remote(self):
        """runtime_overrides can set mode to 'remote'."""
        config = Config.load(runtime_overrides={"mode": "remote"})
        assert config.mode == "remote"

    def test_load_sets_server_url(self):
        """runtime_overrides can set server.url."""
        config = Config.load(
            runtime_overrides={
                "mode": "remote",
                "server": {"url": "http://localhost:8080"},
            }
        )
        assert config.mode == "remote"
        assert config.server.url == "http://localhost:8080"

    def test_load_sets_server_api_key(self):
        """runtime_overrides can set server.api_key."""
        config = Config.load(
            runtime_overrides={
                "server": {"api_key": "sk-test-123"},
            }
        )
        assert config.server.api_key == "sk-test-123"

    def test_load_sets_nested_server_fields(self):
        """runtime_overrides can set multiple server fields at once."""
        config = Config.load(
            runtime_overrides={
                "server": {
                    "url": "http://example.com",
                    "batch_size": 100,
                    "retry_max": 5,
                },
            }
        )
        assert config.server.url == "http://example.com"
        assert config.server.batch_size == 100
        assert config.server.retry_max == 5
        # Unchanged defaults preserved
        assert config.server.flush_interval_ms == 2000


class TestConfigEnvVars:
    """Tests for environment variable handling of mode/server fields."""

    def test_reagent_mode_env_sets_mode(self, monkeypatch):
        """REAGENT_MODE env var sets config.mode."""
        monkeypatch.setenv("REAGENT_MODE", "remote")
        config = Config.load()
        assert config.mode == "remote"

    def test_reagent_server_url_env_sets_server_url(self, monkeypatch):
        """REAGENT_SERVER_URL env var sets config.server.url."""
        monkeypatch.setenv("REAGENT_SERVER_URL", "http://my-server:9090")
        config = Config.load()
        assert config.server.url == "http://my-server:9090"

    def test_reagent_api_key_env_sets_server_api_key(self, monkeypatch):
        """REAGENT_API_KEY env var sets config.server.api_key."""
        monkeypatch.setenv("REAGENT_API_KEY", "sk-from-env")
        config = Config.load()
        assert config.server.api_key == "sk-from-env"

    def test_runtime_overrides_take_precedence_over_env(self, monkeypatch):
        """Runtime overrides beat environment variables."""
        monkeypatch.setenv("REAGENT_MODE", "remote")
        config = Config.load(runtime_overrides={"mode": "local"})
        assert config.mode == "local"


class TestServerConfigValidation:
    """Tests for ServerConfig field validation constraints."""

    def test_batch_size_minimum(self):
        """batch_size must be >= 1."""
        with pytest.raises(Exception):
            ServerConfig(batch_size=0)

    def test_batch_size_maximum(self):
        """batch_size must be <= 1000."""
        with pytest.raises(Exception):
            ServerConfig(batch_size=1001)

    def test_batch_size_valid_boundaries(self):
        """batch_size accepts boundary values 1 and 1000."""
        sc_min = ServerConfig(batch_size=1)
        assert sc_min.batch_size == 1
        sc_max = ServerConfig(batch_size=1000)
        assert sc_max.batch_size == 1000

    def test_flush_interval_ms_minimum(self):
        """flush_interval_ms must be >= 100."""
        with pytest.raises(Exception):
            ServerConfig(flush_interval_ms=99)

    def test_flush_interval_ms_maximum(self):
        """flush_interval_ms must be <= 30000."""
        with pytest.raises(Exception):
            ServerConfig(flush_interval_ms=30001)

    def test_flush_interval_ms_valid_boundaries(self):
        """flush_interval_ms accepts boundary values 100 and 30000."""
        sc_min = ServerConfig(flush_interval_ms=100)
        assert sc_min.flush_interval_ms == 100
        sc_max = ServerConfig(flush_interval_ms=30000)
        assert sc_max.flush_interval_ms == 30000

    def test_timeout_seconds_minimum(self):
        """timeout_seconds must be >= 1."""
        with pytest.raises(Exception):
            ServerConfig(timeout_seconds=0.5)

    def test_timeout_seconds_maximum(self):
        """timeout_seconds must be <= 120."""
        with pytest.raises(Exception):
            ServerConfig(timeout_seconds=121)

    def test_retry_max_minimum(self):
        """retry_max must be >= 0."""
        with pytest.raises(Exception):
            ServerConfig(retry_max=-1)

    def test_retry_max_maximum(self):
        """retry_max must be <= 10."""
        with pytest.raises(Exception):
            ServerConfig(retry_max=11)

    def test_retry_max_zero_is_valid(self):
        """retry_max=0 means no retries and is valid."""
        sc = ServerConfig(retry_max=0)
        assert sc.retry_max == 0

    def test_invalid_batch_size_via_config_load_raises(self):
        """Config.load() raises ConfigError for invalid server.batch_size."""
        with pytest.raises(ConfigError):
            Config.load(runtime_overrides={"server": {"batch_size": -1}})
