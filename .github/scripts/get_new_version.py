"""
Description:
- Print the calculated new version.

Usage:
- python3 update_version.py --current-version <version> (--stage)

Version Scheme:
- <year>.<month>.<release count>(a<prerelease count>)

example:
- case 1:
    - given:
        - current version: 2025.1.1
        - today : YEAR = 2025, MONTH = 1
    - then:
        - if stage is false:
            - new version: 2025.1.2
        - if stage is true:
            - new version: 2025.1.2a0
- case 2:
    - given:
        - current version: 2025.1.2a0
        - today : YEAR = 2025, MONTH = 1
    - then:
        - if stage is false:
            - new version: 2025.1.2
        - if stage is true:
            - new version: 2025.1.2a1
- case 3:
    - given:
        - current version: 2025.1.1
        - today : YEAR = 2025, MONTH = 2
    - then:
        - if stage is false:
            - new version: 2025.2.0
        - if stage is true:
            - new version: 2025.2.0a0
"""

import argparse
import datetime
import typing

import packaging.version

PreType = tuple[typing.Literal["a", "b", "rc"], int] | None


class ArgumentNamespace(argparse.Namespace):
    current: str
    stage: bool = False


def increment_version_count(version: packaging.version.Version, is_stage: bool) -> str:
    if (current_pre := version.pre) and current_pre[0] != "a":
        raise ValueError(f"Unsupported pre-release version: {current_pre[0]}")

    # Get the current date
    today: datetime.date = datetime.date.today()

    # Calculate the new version
    new_count: int = 0
    if version.major == today.year and version.minor == today.month:
        if current_pre:
            # If the current version is a pre-release, do not increment the count
            new_count = version.micro
        else:
            # Same month, increment the count
            new_count = version.micro + 1
    else:
        # Different month, reset the count
        new_count = 1
        current_pre = None

    new_pre: PreType = ((current_pre[0], current_pre[1] + 1) if current_pre else ("a", 0)) if is_stage else None
    new_pre_str = f"{new_pre[0]}{new_pre[1]}" if new_pre else ""
    return f"{today.year}.{today.month}.{new_count}{new_pre_str}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update version in files.")
    parser.add_argument("--current", type=str, required=True)
    parser.add_argument("--stage", default=False, action="store_true")

    args = parser.parse_args(namespace=ArgumentNamespace())
    print(increment_version_count(packaging.version.parse(args.current), args.stage))
