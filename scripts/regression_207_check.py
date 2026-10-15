#!/usr/bin/env python3
"""Regression check for issue #207: importing automedia must not mutate os.environ.

Proves that the lazy ``.env`` overlay keeps import purity:

* importing the product with a populated ``.env`` present leaves the watched
  variables out of ``os.environ`` (pre-fix, the import-time dotenv load pushed
  them in and tripped the pytest environment-leak guard);
* ``load_credential()`` and ``_is_fake_mode()`` still resolve values *from*
  that ``.env``;
* after ``reset_dotenv_overlay_cache()`` a real environment variable set
  afterwards still wins over the overlay.

Safe to run standalone: it writes only under an isolated
``/tmp/automedia/reg207-*`` directory and never touches the real user config.
Exits 0 and prints the marker ``REG207_DOTENV_LAZY_OK`` on success, else exits
non-zero with a diagnostic.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

WATCHLIST = (
    "AUTOMEDIA_MASTER_KEY",
    "AUTOMEDIA_FAKE_LLM",
    "AUTOMEDIA_LLM_API_KEY",
    "AUTOMEDIA_CONFIG_DIR",
)

DOTENV_BODY = "AUTOMEDIA_LLM_API_KEY=reg207-test-key\nAUTOMEDIA_FAKE_LLM=1\n"


def _fail(message: str) -> int:
    print(f"REG207_FAILED: {message}")
    return 1


def main() -> int:
    work_root = Path("/tmp/automedia")  # noqa: S108 — synthetic isolated scratch
    work_root.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="reg207-", dir=str(work_root)))
    try:
        env_path = work_dir / "fake.env"
        env_path.write_text(DOTENV_BODY, encoding="utf-8")

        for name in WATCHLIST:
            os.environ.pop(name, None)
        os.environ["AUTOMEDIA_DOTENV_PATH"] = str(env_path)

        # Product imports happen only after the environment is staged: the
        # import itself is what pre-fix code used to use for the env write.
        from automedia.core.credential_loader import load_credential
        from automedia.core.env_overlay import reset_dotenv_overlay_cache
        from automedia.core.llm_client import _is_fake_mode

        leaked = [name for name in WATCHLIST if name in os.environ]
        if leaked:
            return _fail(f"import mutated os.environ: {sorted(leaked)}")

        credential = load_credential("llm_api_key")
        if credential != "reg207-test-key":
            return _fail(f"load_credential('llm_api_key') == {credential!r}")

        if not _is_fake_mode():
            return _fail("_is_fake_mode() is False; .env value was not honoured")

        reset_dotenv_overlay_cache()
        os.environ["AUTOMEDIA_LLM_API_KEY"] = "real-env-wins"
        if load_credential("llm_api_key") != "real-env-wins":
            return _fail("real env var did not win over the .env overlay after reset")

        leaked = [
            name for name in WATCHLIST if name in os.environ and name != "AUTOMEDIA_LLM_API_KEY"
        ]
        if leaked:
            return _fail(f"resolving credentials mutated os.environ: {sorted(leaked)}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    print("REG207_DOTENV_LAZY_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
