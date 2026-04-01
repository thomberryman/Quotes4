from __future__ import annotations

try:
    import email_validator  # noqa: F401
    from pydantic import EmailStr as PydanticEmailStr
except ImportError:  # pragma: no cover - depends on installed extras
    type EmailAddress = str
else:
    EmailAddress = PydanticEmailStr
