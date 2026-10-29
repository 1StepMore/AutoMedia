#!/usr/bin/env python3
"""Regression check for issues #333/#334: validation runs are sandboxed.

Proves the suite installs both isolation variables and that a scenario command
sees them, so validation can never write the real user config or the repo root.
Exits 0 and prints ``REG333_SANDBOX_ISOLATED`` on success.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from automedia.validation.adapters import CLIAdapter
from automedia.validation.sandbox import validation_sandbox
from automedia.validation.schema import Step


def main() -> int:
    for name in ("AUTOMEDIA_CONFIG_DIR", "AUTOMEDIA_PROJECTS_DIR"):
        os.environ.pop(name, None)
    with validation_sandbox() as sandbox:
        if not sandbox.temporary:
            print("REG333_FAILED: sandbox was not created")
            return 1
        for name, expected in (
            ("AUTOMEDIA_CONFIG_DIR", sandbox.config_dir),
            ("AUTOMEDIA_PROJECTS_DIR", sandbox.projects_dir),
        ):
            if os.environ.get(name) != str(expected):
                print(f"REG333_FAILED: {name} not exported ({os.environ.get(name)!r})")
                return 1
            if not expected.is_dir():
                print(f"REG333_FAILED: {expected} is not a directory")
                return 1
        command = (
            "python3 -c \"import os; print(os.environ['AUTOMEDIA_CONFIG_DIR']); "
            "print(os.environ['AUTOMEDIA_PROJECTS_DIR'])\""
        )
        step = Step.from_dict(
            {
                "name": "echo sandbox",
                "kind": "cli",
                "check": "subprocess sees the sandbox",
                "standard": "tool.contract",
                "command": command,
                "expect": {"success": True},
            }
        )
        result = CLIAdapter().run(step)
        stdout = str(result.output.get("stdout", ""))
        if str(sandbox.config_dir) not in stdout or str(sandbox.projects_dir) not in stdout:
            print(f"REG333_FAILED: subprocess did not inherit the sandbox: {stdout!r}")
            return 1
        root = sandbox.root
    if Path(root).exists():
        print(f"REG333_FAILED: sandbox {root} was not removed")
        return 1
    print("REG333_SANDBOX_ISOLATED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
