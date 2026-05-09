import re

UUID_V4_PATTERN = "[a-f0-9]{8}-?[a-f0-9]{4}-?4[a-f0-9]{3}-?[89ab][a-f0-9]{3}-?[a-f0-9]{12}"
UUID_V4_REGEX = re.compile(f"^{UUID_V4_PATTERN}$", re.IGNORECASE)

# 호스트 형식 — RFC 1035 기반
HOSTNAME_PATTERN = r"^(?=.{1,253}$)([a-z0-9](-?[a-z0-9])*)(\.[a-z0-9](-?[a-z0-9])*)*$"
HOSTNAME_REGEX = re.compile(HOSTNAME_PATTERN)
