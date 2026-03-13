"""ReAgent configuration management.

Configuration is layered with the following precedence (highest to lowest):
1. Runtime overrides (passed to ReAgent constructor)
2. Environment variables (REAGENT_*)
3. Project configuration (.reagent.yml or .reagent.json)
4. User configuration (~/.reagent/config.yml)
5. SDK defaults
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from reagent.core.constants import (
    DEFAULT_BUFFER_SIZE,
    DEFAULT_FLUSH_INTERVAL_MS,
    DEFAULT_STORAGE_PATH,
    DEFAULT_TRANSPORT_MODE,
    DEFAULT_BACKPRESSURE_POLICY,
    DEFAULT_REDACTION_MODE,
    DEFAULT_REPLAY_MODE,
    DEFAULT_OUTPUT_FORMAT,
    TransportMode,
    BackpressurePolicy,
    RedactionMode,
    ReplayMode,
    StorageType,
    OutputFormat,
)
from reagent.core.exceptions import ConfigError


class StorageConfig(BaseModel):
    """Storage backend configuration."""

    type: StorageType = StorageType.JSONL
    path: str = DEFAULT_STORAGE_PATH
    compression: bool = False
    retention_days: int | None = None

    @field_validator("path")
    @classmethod
    def expand_path(cls, v: str) -> str:
        """Expand user home directory and environment variables."""
        return os.path.expandvars(os.path.expanduser(v))


class BufferConfig(BaseModel):
    """Event buffer configuration."""

    size: int = Field(default=DEFAULT_BUFFER_SIZE, ge=100, le=1_000_000)
    flush_interval_ms: int = Field(default=DEFAULT_FLUSH_INTERVAL_MS, ge=10, le=10_000)
    backpressure_policy: BackpressurePolicy = DEFAULT_BACKPRESSURE_POLICY


class RedactionConfig(BaseModel):
    """Redaction engine configuration."""

    enabled: bool = True
    mode: RedactionMode = DEFAULT_REDACTION_MODE
    rules_file: str | None = None
    fields: list[str] = Field(default_factory=list)
    use_nlp: bool = False
    nlp_entities: list[str] | None = None
    nlp_language: str = "en"
    nlp_score_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    timeout_ms: int = Field(default=10, ge=1, le=1000)


class ReplayConfig(BaseModel):
    """Replay engine configuration."""

    default_mode: ReplayMode = DEFAULT_REPLAY_MODE
    sandbox_strict: bool = True
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    checkpoint_interval: int | None = None


class CLIConfig(BaseModel):
    """CLI configuration."""

    default_format: OutputFormat = DEFAULT_OUTPUT_FORMAT
    color_output: bool = True
    pager: str | None = None
    editor: str | None = None


class Config(BaseModel):
    """Main ReAgent configuration."""

    # Transport settings
    transport_mode: TransportMode = DEFAULT_TRANSPORT_MODE

    # Project identification
    project: str | None = None

    # Sub-configurations
    storage: StorageConfig = Field(default_factory=StorageConfig)
    buffer: BufferConfig = Field(default_factory=BufferConfig)
    redaction: RedactionConfig = Field(default_factory=RedactionConfig)
    replay: ReplayConfig = Field(default_factory=ReplayConfig)
    cli: CLIConfig = Field(default_factory=CLIConfig)

    # Debug settings
    debug: bool = False
    verbose: bool = False

    @classmethod
    def load(
        cls,
        config_path: str | Path | None = None,
        runtime_overrides: dict[str, Any] | None = None,
    ) -> Config:
        """Load configuration with layered precedence.

        Args:
            config_path: Optional explicit config file path
            runtime_overrides: Optional runtime configuration overrides

        Returns:
            Merged configuration object

        Raises:
            ConfigError: If configuration is invalid
        """
        # Start with defaults
        config_data: dict[str, Any] = {}

        # Layer 1: User config (~/.reagent/config.yml or config.json)
        user_config = cls._load_user_config()
        config_data = cls._deep_merge(config_data, user_config)

        # Layer 2: Project config (.reagent.yml or .reagent.json)
        project_config = cls._load_project_config(config_path)
        config_data = cls._deep_merge(config_data, project_config)

        # Layer 3: Environment variables
        env_config = cls._load_env_config()
        config_data = cls._deep_merge(config_data, env_config)

        # Layer 4: Runtime overrides
        if runtime_overrides:
            config_data = cls._deep_merge(config_data, runtime_overrides)

        try:
            return cls.model_validate(config_data)
        except Exception as e:
            raise ConfigError(f"Invalid configuration: {e}") from e

    @classmethod
    def _load_user_config(cls) -> dict[str, Any]:
        """Load user-level configuration from ~/.reagent/."""
        home = Path.home()
        config_dir = home / ".reagent"

        for filename in ["config.yml", "config.yaml", "config.json"]:
            config_file = config_dir / filename
            if config_file.exists():
                return cls._load_config_file(config_file)

        return {}

    @classmethod
    def _load_project_config(cls, explicit_path: str | Path | None = None) -> dict[str, Any]:
        """Load project-level configuration."""
        if explicit_path:
            path = Path(explicit_path)
            if path.exists():
                return cls._load_config_file(path)
            raise ConfigError(f"Config file not found: {explicit_path}")

        # Search for config file in current directory and parents
        cwd = Path.cwd()
        for parent in [cwd, *cwd.parents]:
            for filename in [".reagent.yml", ".reagent.yaml", ".reagent.json", "reagent.yml"]:
                config_file = parent / filename
                if config_file.exists():
                    return cls._load_config_file(config_file)

        return {}

    @classmethod
    def _load_config_file(cls, path: Path) -> dict[str, Any]:
        """Load configuration from a file (YAML or JSON)."""
        try:
            content = path.read_text()

            if path.suffix in [".yml", ".yaml"]:
                # Import yaml only when needed
                try:
                    import yaml

                    return yaml.safe_load(content) or {}
                except ImportError:
                    raise ConfigError(
                        "PyYAML is required for YAML config files. "
                        "Install it with: pip install pyyaml"
                    )
            elif path.suffix == ".json":
                return json.loads(content)
            else:
                # Try JSON first, then YAML
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    try:
                        import yaml

                        return yaml.safe_load(content) or {}
                    except ImportError:
                        raise ConfigError(f"Cannot parse config file: {path}")

        except Exception as e:
            if isinstance(e, ConfigError):
                raise
            raise ConfigError(f"Failed to load config file {path}: {e}") from e

    @classmethod
    def _load_env_config(cls) -> dict[str, Any]:
        """Load configuration from environment variables."""
        config: dict[str, Any] = {}

        # Map environment variables to config paths
        env_mapping = {
            "REAGENT_PROJECT": "project",
            "REAGENT_TRANSPORT_MODE": "transport_mode",
            "REAGENT_DEBUG": "debug",
            "REAGENT_VERBOSE": "verbose",
            # Storage
            "REAGENT_STORAGE_TYPE": "storage.type",
            "REAGENT_STORAGE_PATH": "storage.path",
            # Buffer
            "REAGENT_BUFFER_SIZE": "buffer.size",
            "REAGENT_FLUSH_INTERVAL_MS": "buffer.flush_interval_ms",
            # Redaction
            "REAGENT_REDACTION_ENABLED": "redaction.enabled",
            "REAGENT_REDACTION_MODE": "redaction.mode",
            # Replay
            "REAGENT_REPLAY_MODE": "replay.default_mode",
            # CLI
            "REAGENT_OUTPUT_FORMAT": "cli.default_format",
            "REAGENT_COLOR": "cli.color_output",
        }

        for env_var, config_path in env_mapping.items():
            value = os.environ.get(env_var)
            if value is not None:
                cls._set_nested(config, config_path, cls._parse_env_value(value))

        return config

    @staticmethod
    def _parse_env_value(value: str) -> Any:
        """Parse environment variable value to appropriate type."""
        # Boolean values
        if value.lower() in ("true", "1", "yes", "on"):
            return True
        if value.lower() in ("false", "0", "no", "off"):
            return False

        # Try integer
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        return value

    @staticmethod
    def _set_nested(data: dict[str, Any], path: str, value: Any) -> None:
        """Set a nested dictionary value using dot notation."""
        keys = path.split(".")
        current = data

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries, with override taking precedence."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return self.model_dump()
