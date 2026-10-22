#!/usr/bin/env python3
"""Regression lock for issue #263: long Latin topics must stay creatable.

``_slugify()`` has no length cap, and ``Project.init()`` names the project
directory ``YYYYMMDD_<slug>``.  A Latin topic of 247 characters therefore
produced a 256-byte component name and ``mkdir`` raised
``OSError: [Errno 36] File name too long``, so the pipeline died at project
creation with no actionable message.

Failures are collected rather than asserted, so a broken run reports every
violated property at once.  The checks are:

1. the fixture is long enough to cross 255 bytes uncapped (not vacuous);
2. ``slugify_topic()`` clips the Latin slug to 200 UTF-8 bytes;
3. ``Project.init()`` succeeds and its directory name fits;
4. inputs at or below the cap keep their historical slug.
"""

from __future__ import annotations

import os
import sys
import tempfile

from automedia.core.project import Project, slugify_topic

MARKER = "SLUG_LONG_TOPIC_FITS_FILESYSTEM"
MAX_COMPONENT_BYTES = 255
MAX_SLUG_BYTES = 200
LONG_TOPIC = "x" * 300


def main() -> int:
    failures: list[str] = []

    uncapped_bytes = len(f"20261022_{LONG_TOPIC}".encode())
    if uncapped_bytes <= MAX_COMPONENT_BYTES:
        failures.append(
            f"fixture is {uncapped_bytes} bytes uncapped (vacuous, expected > "
            f"{MAX_COMPONENT_BYTES})"
        )

    slug_bytes = len(slugify_topic(LONG_TOPIC).encode("utf-8"))
    if slug_bytes > MAX_SLUG_BYTES:
        failures.append(f"slug is {slug_bytes} bytes, expected <= {MAX_SLUG_BYTES}")

    with tempfile.TemporaryDirectory() as base_dir:
        project = Project.init(LONG_TOPIC, "acme", base_dir=base_dir)
        dirname = os.path.basename(project.project_dir)
        name_bytes = len(dirname.encode("utf-8"))
        if name_bytes > MAX_COMPONENT_BYTES:
            failures.append(
                f"directory name is {name_bytes} bytes, expected <= {MAX_COMPONENT_BYTES}"
            )
        if not os.path.isdir(project.project_dir):
            failures.append("project directory was not created")

    for topic, expected in (
        ("y" * 200, "y" * 200),
        ("AutoMedia 2024 项目启动", "automedia-2024-项目启动"),
        ("Hello World", "hello-world"),
        ("小团队内容排期的实用做法", "小团队内容排期的实用做法"),
    ):
        actual = slugify_topic(topic)
        if actual != expected:
            failures.append(f"{topic[:32]!r} -> {actual!r}, expected {expected!r}")

    if failures:
        for line in failures:
            print(f"ISSUE263_GUARD_MISSING: {line}", file=sys.stderr)
        return 1

    print(MARKER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
