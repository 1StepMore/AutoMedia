#!/usr/bin/env python3
"""Regression check for issue #83: model config fallback preservation.

Proves that ``save_model_config`` deep-merges a partial update into an
existing ``model_config.yaml`` so an existing LLM ``fallback`` chain is
preserved while provider/model are updated (the fix for #83, where a
destructive full-file overwrite silently dropped the fallback chain).

Safe to run standalone: it writes only to an isolated ``/tmp/automedia/reg83/``
directory and never touches the real user config. Exits 0 and prints the
marker ``REG83_FALLBACK_PRESERVED`` on success, else exits non-zero.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

from automedia.manifests.model_config_schema import save_model_config


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="reg83-") as tmp:
        cfg = Path(tmp) / "model_config.yaml"
        # Seed a config with an existing fallback chain.
        cfg.write_text(
            "llm:\n"
            "  text_generation:\n"
            "    provider: old-provider\n"
            "    model: old-model\n"
            "    fallback:\n"
            "      - provider: fb-provider\n"
            "        model: fb-model\n",
            encoding="utf-8",
        )

        # Update only the primary provider/model; the fallback must survive.
        save_model_config(
            str(cfg),
            {"llm": {"text_generation": {"provider": "deepseek", "model": "deepseek-chat"}}},
        )

        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        tg = data.get("llm", {}).get("text_generation", {})
        fallback = tg.get("fallback", [])
        preserved = (
            bool(fallback)
            and fallback[0].get("provider") == "fb-provider"
            and tg.get("provider") == "deepseek"
            and tg.get("model") == "deepseek-chat"
        )
        if not preserved:
            print(f"FALLBACK_MISSING: provider={tg.get('provider')!r} fallback={fallback!r}")
            return 1

    print("REG83_FALLBACK_PRESERVED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
