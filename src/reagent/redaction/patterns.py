"""Regex patterns for sensitive data detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern as RegexPattern


@dataclass
class Pattern:
    """A named pattern for detecting sensitive data."""

    name: str
    regex: RegexPattern[str]
    description: str
    category: str = "pii"

    @classmethod
    def from_string(cls, name: str, pattern: str, description: str, category: str = "pii") -> Pattern:
        """Create a Pattern from a regex string."""
        return cls(
            name=name,
            regex=re.compile(pattern, re.IGNORECASE),
            description=description,
            category=category,
        )

    def find_all(self, text: str) -> list[tuple[int, int, str]]:
        """Find all matches in text.

        Returns:
            List of (start, end, matched_text) tuples
        """
        matches = []
        for match in self.regex.finditer(text):
            matches.append((match.start(), match.end(), match.group()))
        return matches


# API Key Patterns
API_KEY_PATTERNS = [
    Pattern.from_string(
        name="openai_api_key",
        pattern=r"sk-[a-zA-Z0-9]{20,}",
        description="OpenAI API Key",
        category="secrets",
    ),
    Pattern.from_string(
        name="anthropic_api_key",
        pattern=r"sk-ant-[a-zA-Z0-9\-]{20,}",
        description="Anthropic API Key",
        category="secrets",
    ),
    Pattern.from_string(
        name="aws_access_key",
        pattern=r"AKIA[0-9A-Z]{16}",
        description="AWS Access Key ID",
        category="secrets",
    ),
    Pattern.from_string(
        name="aws_secret_key",
        pattern=r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])",
        description="AWS Secret Access Key",
        category="secrets",
    ),
    Pattern.from_string(
        name="github_token",
        pattern=r"gh[ps]_[A-Za-z0-9_]{36,}",
        description="GitHub Token",
        category="secrets",
    ),
    Pattern.from_string(
        name="github_oauth",
        pattern=r"gho_[A-Za-z0-9_]{36,}",
        description="GitHub OAuth Token",
        category="secrets",
    ),
    Pattern.from_string(
        name="slack_token",
        pattern=r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24}",
        description="Slack Token",
        category="secrets",
    ),
    Pattern.from_string(
        name="stripe_key",
        pattern=r"sk_live_[0-9a-zA-Z]{24,}",
        description="Stripe Secret Key",
        category="secrets",
    ),
    Pattern.from_string(
        name="stripe_restricted",
        pattern=r"rk_live_[0-9a-zA-Z]{24,}",
        description="Stripe Restricted Key",
        category="secrets",
    ),
    Pattern.from_string(
        name="google_api_key",
        pattern=r"AIza[0-9A-Za-z\-_]{35}",
        description="Google API Key",
        category="secrets",
    ),
    Pattern.from_string(
        name="generic_api_key",
        pattern=r"(?i)(api[_-]?key|apikey|api[_-]?secret)['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{20,})['\"]?",
        description="Generic API Key Pattern",
        category="secrets",
    ),
    Pattern.from_string(
        name="bearer_token",
        pattern=r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}",
        description="Bearer Token",
        category="secrets",
    ),
    Pattern.from_string(
        name="basic_auth",
        pattern=r"(?i)basic\s+[a-zA-Z0-9+/=]{20,}",
        description="Basic Auth Header",
        category="secrets",
    ),
]

# Credit Card Pattern (Luhn algorithm check should be done separately)
CREDIT_CARD_PATTERN = Pattern.from_string(
    name="credit_card",
    pattern=r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})\b",
    description="Credit Card Number",
    category="pii",
)

# Credit Card with separators
CREDIT_CARD_WITH_SEPARATORS = Pattern.from_string(
    name="credit_card_separated",
    pattern=r"\b(?:\d{4}[- ]){3}\d{4}\b",
    description="Credit Card Number with separators",
    category="pii",
)

# SSN Pattern (US Social Security Number)
SSN_PATTERN = Pattern.from_string(
    name="ssn",
    pattern=r"\b(?!000|666|9\d{2})\d{3}[-\s]?(?!00)\d{2}[-\s]?(?!0000)\d{4}\b",
    description="US Social Security Number",
    category="pii",
)

# Email Pattern
EMAIL_PATTERN = Pattern.from_string(
    name="email",
    pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    description="Email Address",
    category="pii",
)

# Phone Pattern (US format)
PHONE_PATTERN = Pattern.from_string(
    name="phone",
    pattern=r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b",
    description="US Phone Number",
    category="pii",
)

# IP Address Pattern
IP_ADDRESS_PATTERN = Pattern.from_string(
    name="ip_address",
    pattern=r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
    description="IPv4 Address",
    category="pii",
)

# Password in URL
PASSWORD_IN_URL = Pattern.from_string(
    name="password_in_url",
    pattern=r"(?i)(?:https?://)[^:]+:([^@]+)@",
    description="Password in URL",
    category="secrets",
)

# Private Key Pattern
PRIVATE_KEY_PATTERN = Pattern.from_string(
    name="private_key",
    pattern=r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----",
    description="Private Key Header",
    category="secrets",
)

# JWT Token Pattern
JWT_PATTERN = Pattern.from_string(
    name="jwt",
    pattern=r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+",
    description="JWT Token",
    category="secrets",
)

# Default patterns to use
DEFAULT_PATTERNS = [
    *API_KEY_PATTERNS,
    CREDIT_CARD_PATTERN,
    CREDIT_CARD_WITH_SEPARATORS,
    SSN_PATTERN,
    EMAIL_PATTERN,
    PHONE_PATTERN,
    IP_ADDRESS_PATTERN,
    PASSWORD_IN_URL,
    PRIVATE_KEY_PATTERN,
    JWT_PATTERN,
]


def get_patterns_by_category(category: str) -> list[Pattern]:
    """Get all patterns in a category."""
    return [p for p in DEFAULT_PATTERNS if p.category == category]


def get_secret_patterns() -> list[Pattern]:
    """Get all secret/API key patterns."""
    return get_patterns_by_category("secrets")


def get_pii_patterns() -> list[Pattern]:
    """Get all PII patterns."""
    return get_patterns_by_category("pii")
