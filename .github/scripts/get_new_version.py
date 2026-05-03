"""
Description:
- Print the calculated new release tag.
- Reads all existing git tags, picks the highest PEP440 version as the base,
  and computes the next version. Optionally removes invalid (b/rc) pre-release
  tags so they cannot poison future runs.

Usage:
- python3 get_new_version.py [--stage] [--cleanup-invalid]

Version Scheme:
- <year>.<month>.<release count>(a<prerelease count>)

example:
- case 1:
    - given:
        - latest version: 2025.1.1
        - today : YEAR = 2025, MONTH = 1
    - then:
        - if stage is false:
            - new version: 2025.1.2
        - if stage is true:
            - new version: 2025.1.2a0
- case 2:
    - given:
        - latest version: 2025.1.2a0
        - today : YEAR = 2025, MONTH = 1
    - then:
        - if stage is false:
            - new version: 2025.1.2
        - if stage is true:
            - new version: 2025.1.2a1
- case 3:
    - given:
        - latest version: 2025.1.1
        - today : YEAR = 2025, MONTH = 2
    - then:
        - if stage is false:
            - new version: 2025.2.1
        - if stage is true:
            - new version: 2025.2.1a0
- case 4:
    - given:
        - no tags exist
        - today : YEAR = 2025, MONTH = 2
    - then:
        - if stage is false:
            - new version: 2025.2.1
        - if stage is true:
            - new version: 2025.2.1a0
"""

import argparse
import datetime
import subprocess  # nosec: B404 — git CLI 호출 전용, 입력은 PEP440 검증을 통과한 태그 이름뿐
import sys
import typing

import packaging.version

PreType = tuple[typing.Literal["a", "b", "rc"], int] | None


class ArgumentNamespace(argparse.Namespace):
    stage: bool = False
    cleanup_invalid: bool = False


def list_tags() -> list[str]:
    out = subprocess.run(  # nosec: B603 B607 — 고정 인자, CI 신뢰 환경
        ["git", "tag", "-l"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def collect_versions(tags: list[str]) -> tuple[list[packaging.version.Version], list[str]]:
    """Split tags into (a-only PEP440 versions, invalid b/rc tags). Non-PEP440 tags are ignored."""
    valid: list[packaging.version.Version] = []
    invalid: list[str] = []
    for tag in tags:
        try:
            version = packaging.version.parse(tag)
        except packaging.version.InvalidVersion:
            continue
        if version.pre and version.pre[0] != "a":
            invalid.append(tag)
            continue
        valid.append(version)
    return valid, invalid


def tag_exists(tag: str) -> bool:
    return (
        subprocess.run(  # nosec: B603 B607 — 고정 인자, CI 신뢰 환경
            ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"],
            capture_output=True,
        ).returncode
        == 0
    )


def delete_tag(tag: str) -> None:
    subprocess.run(  # nosec: B603 B607 — 고정 인자, CI 신뢰 환경
        ["git", "tag", "-d", tag],
        check=False,
        capture_output=True,
    )
    result = subprocess.run(  # nosec: B603 B607 — 고정 인자, CI 신뢰 환경
        ["git", "push", "origin", f":refs/tags/{tag}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Warning: failed to delete remote tag {tag}: {result.stderr.strip()}", file=sys.stderr)


def increment_version_count(version: packaging.version.Version | None, is_stage: bool) -> str:
    today: datetime.date = datetime.date.today()
    current_pre: PreType = typing.cast(PreType, version.pre) if version else None

    new_count: int
    if version and version.major == today.year and version.minor == today.month:
        if current_pre:
            # Same month with a pre-release: keep the same micro
            new_count = version.micro
        else:
            # Same month, increment the count
            new_count = version.micro + 1
    else:
        # Different month or no prior version: start fresh
        new_count = 1
        current_pre = None

    new_pre: PreType = ((current_pre[0], current_pre[1] + 1) if current_pre else ("a", 0)) if is_stage else None
    new_pre_str = f"{new_pre[0]}{new_pre[1]}" if new_pre else ""
    return f"{today.year}.{today.month}.{new_count}{new_pre_str}"


def compute_next_tag(latest: packaging.version.Version | None, is_stage: bool) -> str:
    candidate = increment_version_count(latest, is_stage)
    while tag_exists(candidate):
        print(f"Warning: tag {candidate} already exists, retrying", file=sys.stderr)
        candidate = increment_version_count(packaging.version.parse(candidate), is_stage)
    return candidate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute next release tag.")
    parser.add_argument("--stage", default=False, action="store_true")
    parser.add_argument(
        "--cleanup-invalid",
        default=False,
        action="store_true",
        help="Delete any b/rc pre-release tags (locally and on origin) before computing the next tag.",
    )

    args = parser.parse_args(namespace=ArgumentNamespace())

    valid, invalid = collect_versions(list_tags())

    if args.cleanup_invalid:
        for tag in invalid:
            print(f"Removing invalid pre-release tag: {tag}", file=sys.stderr)
            delete_tag(tag)

    latest = max(valid) if valid else None
    print(compute_next_tag(latest, args.stage))
