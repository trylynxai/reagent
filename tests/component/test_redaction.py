"""Component tests for redaction engine."""

import pytest

from reagent.redaction.patterns import (
    Pattern,
    DEFAULT_PATTERNS,
    API_KEY_PATTERNS,
    CREDIT_CARD_PATTERN,
    SSN_PATTERN,
    EMAIL_PATTERN,
)
from reagent.redaction.rules import RedactionRule, RedactionRuleSet
from reagent.redaction.engine import RedactionEngine
from reagent.core.constants import RedactionMode


class TestPatterns:
    """Tests for redaction patterns."""

    def test_openai_api_key(self):
        """Test OpenAI API key detection."""
        text = "My API key is sk-1234567890abcdefghijklmnopqrstuvwxyz123456"
        pattern = next(p for p in API_KEY_PATTERNS if p.name == "openai_api_key")
        matches = pattern.find_all(text)
        assert len(matches) == 1
        assert "sk-" in matches[0][2]

    def test_aws_access_key(self):
        """Test AWS access key detection."""
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        pattern = next(p for p in API_KEY_PATTERNS if p.name == "aws_access_key")
        matches = pattern.find_all(text)
        assert len(matches) == 1
        assert matches[0][2] == "AKIAIOSFODNN7EXAMPLE"

    def test_credit_card(self):
        """Test credit card detection."""
        text = "Card number: 4111111111111111"
        matches = CREDIT_CARD_PATTERN.find_all(text)
        assert len(matches) == 1

    def test_ssn(self):
        """Test SSN detection."""
        text = "SSN: 123-45-6789"
        matches = SSN_PATTERN.find_all(text)
        assert len(matches) == 1

    def test_email(self):
        """Test email detection."""
        text = "Contact me at test@example.com"
        matches = EMAIL_PATTERN.find_all(text)
        assert len(matches) == 1
        assert matches[0][2] == "test@example.com"


class TestRedactionRules:
    """Tests for redaction rules."""

    def test_rule_replacement_remove(self):
        """Test remove mode replacement."""
        rule = RedactionRule(pattern_name="test", mode=RedactionMode.REMOVE)
        replacement = rule.get_replacement("secret123", "test")
        assert "[REDACTED:TEST]" in replacement

    def test_rule_replacement_hash(self):
        """Test hash mode replacement."""
        rule = RedactionRule(pattern_name="test", mode=RedactionMode.HASH)
        replacement = rule.get_replacement("secret123", "test")
        assert "[HASH:" in replacement

    def test_rule_replacement_mask(self):
        """Test mask mode replacement."""
        rule = RedactionRule(
            pattern_name="test",
            mode=RedactionMode.MASK,
            mask_chars=4,
            mask_position="end",
        )
        replacement = rule.get_replacement("secret123456", "test")
        assert replacement.endswith("3456")
        assert "*" in replacement

    def test_rule_set_get_rule(self):
        """Test getting rules from rule set."""
        rules = RedactionRuleSet(
            rules=[
                RedactionRule(pattern_name="email", mode=RedactionMode.HASH),
            ],
            default_mode=RedactionMode.REMOVE,
        )

        # Specific rule
        email_rule = rules.get_rule("email")
        assert email_rule.mode == RedactionMode.HASH

        # Default rule
        other_rule = rules.get_rule("unknown")
        assert other_rule.mode == RedactionMode.REMOVE

    def test_rule_set_field_checking(self):
        """Test field name checking."""
        rules = RedactionRuleSet()

        # Should always redact password fields
        assert rules.should_redact_field("password") is True
        assert rules.should_redact_field("user_password") is True
        assert rules.should_redact_field("api_key") is True

        # Should not have preference for other fields
        assert rules.should_redact_field("username") is None


class TestRedactionEngine:
    """Tests for RedactionEngine."""

    @pytest.fixture
    def engine(self):
        """Create a redaction engine for testing."""
        return RedactionEngine()

    def test_redact_api_key(self, engine):
        """Test redacting API keys."""
        text = "Use this key: sk-1234567890abcdefghijklmnopqrstuvwxyz123456"
        result = engine.redact(text)

        assert result.had_redactions is True
        assert "sk-" not in result.redacted_value
        assert len(result.redactions) == 1

    def test_redact_email(self, engine):
        """Test redacting emails."""
        text = "Contact user@example.com for help"
        result = engine.redact(text)

        assert result.had_redactions is True
        assert "user@example.com" not in result.redacted_value

    def test_redact_credit_card(self, engine):
        """Test redacting credit card numbers."""
        text = "Payment with card 4111111111111111"
        result = engine.redact(text)

        assert result.had_redactions is True
        assert "4111111111111111" not in result.redacted_value

    def test_no_redaction_needed(self, engine):
        """Test when no redaction is needed."""
        text = "This is a normal text without sensitive data"
        result = engine.redact(text)

        assert result.had_redactions is False
        assert result.redacted_value == text

    def test_redact_dict(self, engine):
        """Test redacting a dictionary."""
        data = {
            "username": "john",
            "password": "secret123",
            "email": "john@example.com",
            "nested": {
                "api_key": "sk-1234567890abcdefghijklmnopqrstuv123456",
            },
        }

        result = engine.redact_dict(data)

        # Password field should be redacted by field name
        assert result["password"] != "secret123"

        # Email should be redacted by content
        assert "john@example.com" not in str(result["email"])

    def test_redact_disabled(self):
        """Test when redaction is disabled."""
        rules = RedactionRuleSet(enabled=False)
        engine = RedactionEngine(rules=rules)

        text = "API key: sk-1234567890abcdefghijklmnopqrstuv123456"
        result = engine.redact(text)

        assert result.had_redactions is False
        assert result.redacted_value == text

    def test_custom_pattern(self, engine):
        """Test adding a custom pattern."""
        custom = Pattern.from_string(
            name="custom_id",
            pattern=r"CUSTOM-\d{6}",
            description="Custom ID pattern",
        )
        engine.add_pattern(custom)

        text = "ID: CUSTOM-123456"
        result = engine.redact(text)

        assert result.had_redactions is True
        assert "CUSTOM-123456" not in result.redacted_value
