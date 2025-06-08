import re

UUID_V4_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
UUID_V4_REGEX = re.compile(f"^{UUID_V4_PATTERN}$", re.IGNORECASE)
