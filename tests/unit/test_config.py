"""Unit tests for configuration."""

import os
import pytest
from pathlib import Path

from reagent.core.config import Config, StorageConfig, RedactionConfig
from reagent.core.constants import TransportMode, StorageType, RedactionMode
from reagent.core.exceptions import ConfigError


class TestStorageConfig:
    """Tests for StorageConfig model."""

    def test_defaults(self):
        """Test default storage configuration."""
        config = StorageConfig()
        assert config.type == StorageType.JSONL
        assert config.compression is False

    def test_path_expansion(self):
        """Test path expansion for user home directory."""
        config = StorageConfig(path="~/traces")
        assert not config.path.startswith("~")
        assert Path.home().as_posix() in config.path


class TestRedactionConfig:
    """Tests for RedactionConfig model."""

    def test_defaults(self):
        """Test default redaction configuration."""
        config = RedactionConfig()
        assert config.enabled is True
        assert config.mode == RedactionMode.REMOVE
        assert config.use_nlp is False

    def test_custom_values(self):
        """Test custom redaction configuration."""
        config = RedactionConfig(
            enabled=True,
            mode=RedactionMode.HASH,
            fields=["password", "api_key"],
        )
        assert config.mode == RedactionMode.HASH
        assert "password" in config.fields


class TestConfig:
    """Tests for main Config model."""

    def test_defaults(self):
        """Test default configuration values."""
        config = Config()
        assert config.transport_mode == TransportMode.BUFFERED
        assert config.debug is False
        assert config.storage.type == StorageType.JSONL

    def test_with_overrides(self):
        """Test configuration with custom values."""
        config = Config(
            transport_mode=TransportMode.SYNC,
            project="my-project",
            debug=True,
        )
        assert config.transport_mode == TransportMode.SYNC
        assert config.project == "my-project"
        assert config.debug is True

    def test_to_dict(self):
        """Test configuration to dictionary conversion."""
        config = Config(project="test")
        data = config.to_dict()

        assert isinstance(data, dict)
        assert data["project"] == "test"
        assert "storage" in data
        assert "buffer" in data

    def test_load_with_runtime_overrides(self):
        """Test loading configuration with runtime overrides."""
        config = Config.load(
            runtime_overrides={
                "project": "override-project",
                "debug": True,
            }
        )

        assert config.project == "override-project"
        assert config.debug is True

    def test_env_config_loading(self, monkeypatch):
        """Test loading configuration from environment variables."""
        monkeypatch.setenv("REAGENT_PROJECT", "env-project")
        monkeypatch.setenv("REAGENT_DEBUG", "true")
        monkeypatch.setenv("REAGENT_BUFFER_SIZE", "5000")

        config = Config.load()

        assert config.project == "env-project"
        assert config.debug is True
        assert config.buffer.size == 5000

    def test_env_value_parsing(self):
        """Test parsing of environment variable values."""
        # Boolean values
        assert Config._parse_env_value("true") is True
        assert Config._parse_env_value("false") is False
        assert Config._parse_env_value("yes") is True
        assert Config._parse_env_value("no") is False

        # Integer values
        assert Config._parse_env_value("42") == 42

        # Float values
        assert Config._parse_env_value("3.14") == 3.14

        # String values
        assert Config._parse_env_value("hello") == "hello"

    def test_deep_merge(self):
        """Test deep merge of configuration dictionaries."""
        base = {
            "a": 1,
            "b": {"c": 2, "d": 3},
        }
        override = {
            "b": {"c": 4},
            "e": 5,
        }

        result = Config._deep_merge(base, override)

        assert result["a"] == 1
        assert result["b"]["c"] == 4  # Overridden
        assert result["b"]["d"] == 3  # Preserved
        assert result["e"] == 5  # Added
