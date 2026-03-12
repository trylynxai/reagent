"""Redaction rules configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reagent.core.constants import RedactionMode


@dataclass
class RedactionRule:
    """A rule for redacting sensitive data.

    Attributes:
        pattern_name: Name of the pattern to match (or "*" for all)
        mode: How to redact (remove, hash, mask, encrypt)
        replacement: Custom replacement text (for remove mode)
        mask_chars: Number of characters to show (for mask mode)
        mask_position: Where to show chars ("start", "end", "both")
    """

    pattern_name: str
    mode: RedactionMode = RedactionMode.REMOVE
    replacement: str | None = None
    mask_chars: int = 4
    mask_position: str = "end"  # "start", "end", "both"

    def get_replacement(self, original: str, pattern_name: str) -> str:
        """Get the replacement text for a matched value.

        Args:
            original: The original matched text
            pattern_name: Name of the pattern that matched

        Returns:
            The replacement text
        """
        if self.mode == RedactionMode.REMOVE:
            if self.replacement:
                return self.replacement
            return f"[REDACTED:{pattern_name.upper()}]"

        elif self.mode == RedactionMode.HASH:
            import hashlib
            hash_value = hashlib.sha256(original.encode()).hexdigest()[:16]
            return f"[HASH:{hash_value}]"

        elif self.mode == RedactionMode.MASK:
            if len(original) <= self.mask_chars:
                return "*" * len(original)

            if self.mask_position == "start":
                visible = original[:self.mask_chars]
                masked = "*" * (len(original) - self.mask_chars)
                return f"{visible}{masked}"
            elif self.mask_position == "end":
                masked = "*" * (len(original) - self.mask_chars)
                visible = original[-self.mask_chars:]
                return f"{masked}{visible}"
            else:  # both
                half_chars = self.mask_chars // 2
                start_visible = original[:half_chars]
                end_visible = original[-(self.mask_chars - half_chars):]
                masked = "*" * (len(original) - self.mask_chars)
                return f"{start_visible}{masked}{end_visible}"

        elif self.mode == RedactionMode.ENCRYPT:
            # Encryption would require a key, return placeholder
            return f"[ENCRYPTED:{pattern_name.upper()}]"

        return f"[REDACTED:{pattern_name.upper()}]"


@dataclass
class RedactionRuleSet:
    """A set of redaction rules with priority handling.

    Rules are applied in order, with more specific rules taking precedence.
    """

    rules: list[RedactionRule] = field(default_factory=list)
    default_mode: RedactionMode = RedactionMode.REMOVE
    enabled: bool = True

    # Fields that should always be redacted
    always_redact_fields: list[str] = field(default_factory=lambda: [
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "api-key",
        "authorization",
        "auth",
        "credentials",
    ])

    # Fields that should never be redacted
    never_redact_fields: list[str] = field(default_factory=list)

    def get_rule(self, pattern_name: str) -> RedactionRule:
        """Get the rule for a pattern.

        Args:
            pattern_name: Name of the pattern

        Returns:
            The applicable rule (specific or default)
        """
        # Look for specific rule
        for rule in self.rules:
            if rule.pattern_name == pattern_name:
                return rule

        # Look for wildcard rule
        for rule in self.rules:
            if rule.pattern_name == "*":
                return rule

        # Return default rule
        return RedactionRule(pattern_name="*", mode=self.default_mode)

    def should_redact_field(self, field_name: str) -> bool | None:
        """Check if a field should be redacted based on its name.

        Args:
            field_name: Name of the field

        Returns:
            True if should redact, False if should not, None if no preference
        """
        field_lower = field_name.lower()

        # Check never-redact list
        for pattern in self.never_redact_fields:
            if pattern.lower() in field_lower:
                return False

        # Check always-redact list
        for pattern in self.always_redact_fields:
            if pattern.lower() in field_lower:
                return True

        return None

    def add_rule(self, rule: RedactionRule) -> None:
        """Add a rule to the set."""
        self.rules.append(rule)

    def remove_rule(self, pattern_name: str) -> bool:
        """Remove a rule by pattern name.

        Returns:
            True if rule was removed
        """
        for i, rule in enumerate(self.rules):
            if rule.pattern_name == pattern_name:
                del self.rules[i]
                return True
        return False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RedactionRuleSet:
        """Create a rule set from a dictionary configuration.

        Example config:
        {
            "enabled": true,
            "default_mode": "remove",
            "always_redact_fields": ["password", "secret"],
            "never_redact_fields": ["username"],
            "rules": [
                {"pattern_name": "email", "mode": "hash"},
                {"pattern_name": "credit_card", "mode": "mask", "mask_chars": 4}
            ]
        }
        """
        rules = []
        for rule_data in data.get("rules", []):
            mode = rule_data.get("mode", "remove")
            if isinstance(mode, str):
                mode = RedactionMode(mode)
            rules.append(RedactionRule(
                pattern_name=rule_data["pattern_name"],
                mode=mode,
                replacement=rule_data.get("replacement"),
                mask_chars=rule_data.get("mask_chars", 4),
                mask_position=rule_data.get("mask_position", "end"),
            ))

        default_mode = data.get("default_mode", "remove")
        if isinstance(default_mode, str):
            default_mode = RedactionMode(default_mode)

        return cls(
            rules=rules,
            default_mode=default_mode,
            enabled=data.get("enabled", True),
            always_redact_fields=data.get("always_redact_fields", cls.always_redact_fields),
            never_redact_fields=data.get("never_redact_fields", []),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary configuration."""
        return {
            "enabled": self.enabled,
            "default_mode": self.default_mode.value,
            "always_redact_fields": self.always_redact_fields,
            "never_redact_fields": self.never_redact_fields,
            "rules": [
                {
                    "pattern_name": rule.pattern_name,
                    "mode": rule.mode.value,
                    "replacement": rule.replacement,
                    "mask_chars": rule.mask_chars,
                    "mask_position": rule.mask_position,
                }
                for rule in self.rules
            ],
        }
