#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main() -> None:
    """Run administrative tasks."""
    # WeasyPrint dlopen()s Homebrew's pango/cairo at import time; macOS needs them on dyld's path.
    if sys.platform == "darwin":
        fallback = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        if "/opt/homebrew/lib" not in fallback.split(":"):
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(filter(None, ["/opt/homebrew/lib", fallback]))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
