from base64 import urlsafe_b64decode, urlsafe_b64encode
from uuid import UUID

from core.const.regex import UUID_V4_REGEX


def uuid_to_b64(in_str: UUID | str) -> str:
    if isinstance(in_str, str):
        if not UUID_V4_REGEX.match(in_str):
            raise ValueError(f"Invalid UUID string: {in_str}")
        in_str = UUID(in_str)

    return urlsafe_b64encode(in_str.bytes).decode("utf-8").rstrip("=")


def b64_to_uuid(in_str: str) -> UUID:
    return UUID(bytes=urlsafe_b64decode(in_str + "=" * (-len(in_str) % 4)))
