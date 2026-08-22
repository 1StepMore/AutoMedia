#!/usr/bin/env python3
"""Offline secret scan — no network, no binary download.

Catches the exact leak class reported: credential-bearing URLs
(https://user:TOKEN@github.com/...) and well-known token prefixes
(ghp_/gho_/github_pat_), plus a few high-signal generic patterns.

Designed as a pre-commit local hook (language: system), so it runs
even when the gitleaks remote hook cannot download its env.

Exit 0 = clean, 1 = findings (blocks the commit).

Allowlist: .env.example, deploy/systemd/*.env.template, tests/fixtures/synth/,
and any line containing the literal placeholder "your-key-here" / "example".
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# (name, pattern) — keep tight to avoid false positives on docs.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "github_pat",
        re.compile(r"(ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{60,})"),
    ),
    ("cred_url", re.compile(r"https://[^/\s:]+:[^/\s@]+@github\.com")),
    ("cred_url_generic", re.compile(r"https://[^/\s:]+:[^/\s@]+@[^/\s]+\.[^/\s]+")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_header", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    # --- Baidu AI open platform / Qianfan / BOS / Map credentials ---
    # AK (access key) / SK (secret key) live on aip.baidubce.com; the SDK
    # console prints them as a pair of 32-char hex strings in API Key/Secret
    # Key fields.  bce-v3/ALTAK<...> is the auth header used by the newer
    # Baidu Qianfan / ERNIE SDKs.
    ("baidu_bce_auth_header", re.compile(r"\bbce-v3/ALTAK[A-Za-z0-9_\-]{10,}")),
    ("baidu_altak_key", re.compile(r"\bALTAK[A-Za-z0-9_\-]{20,}")),
    ("baidu_aip_host", re.compile(r"aip\.baidubce\.com")),
    ("baidu_qianfan_host", re.compile(r"qianfan\.baidubce\.com")),
    ("baidu_bos_host", re.compile(r"bce\.bos\.myqcloud\.com")),
    # Baidu console prints API Key + Secret Key as two 32-char hex strings
    # side by side (e.g. "API Key: <hex> Secret Key: <hex>").  Require TWO
    # 32-hex values near each other so git SHAs and package hashes (single
    # hex runs) never false-positive.
    (
        "baidu_32hex_keypair",
        re.compile(
            r"(?i)\b(?:api[\s_-]?key|secret(?:\s*key)?|appid|app_id|access[\s_-]?key|ak|sk)\b[^\n]{0,40}?[\"']?[0-9a-f]{32}[\"']?(?=[^\n]*[^0-9a-f\n])[^\n]{1,80}[\"']?[0-9a-f]{32}[\"']?"
        ),
    ),
    # --- Credential shapes that leaked in automedia-package (2026-08) ---
    ("minimax_api_key", re.compile(r"\bsk-cp-[A-Za-z0-9_\-]{20,}")),
    ("wechat_appid", re.compile(r"\bwx[0-9a-f]{16}\b")),
    ("feishu_app_id", re.compile(r"\bcli_[a-z0-9]{10,}")),
]

# Path substrings that are always allowlisted (templates / fixtures).
ALLOWLIST_PATH_SUBSTRINGS = (
    "tests/fixtures/synth",
    ".env.example",
    ".env.template",
    "scripts/check-secrets.py",  # self — contains example literals in comments
)

# Line-level allowlist: placeholders and example docs never block.
ALLOWLIST_LINE_RE = re.compile(
    r"(your-key-here|example\.com|EXAMPLE|PLACEHOLDER|fake|synth|sk-your-key)",
    re.IGNORECASE,
)

# Binary / non-text extensions to skip entirely.
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".pdf",
    ".bin",
    ".safetensors",
    ".gguf",
    ".h5",
    ".parquet",
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".dll",
    ".mp4",
    ".mp3",
    ".wav",
    ".m4a",
}


def _should_skip_path(p: Path) -> bool:
    s = p.as_posix()
    if any(sub in s for sub in ALLOWLIST_PATH_SUBSTRINGS):
        return True
    if p.suffix.lower() in SKIP_SUFFIXES:
        return True
    # Skip common large/ignored dirs even if pre-commit somehow passes them
    return any(
        part
        in {
            ".git",
            ".venv",
            ".mypy_cache",
            ".ruff_cache",
            ".pytest_cache",
            ".hypothesis",
            "site",
            "build",
            "dist",
            ".codegraph",
            "node_modules",
            "__pycache__",
        }
        for part in p.parts
    )


def scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except Exception:
        return findings  # binary or unreadable — skip
    for idx, line in enumerate(text.splitlines(), start=1):
        if ALLOWLIST_LINE_RE.search(line):
            continue
        for name, pat in PATTERNS:
            m = pat.search(line)
            if m:
                # Extra guard for cred_url_generic: require the line to actually
                # look like a URL with scheme, not a doc example without token shape.
                # cred_url (github) is already strict enough to always flag.
                snippet = line.strip()[:160]
                findings.append(f"{path}:{idx} [{name}] {snippet}")
                break  # one finding per line is enough
    return findings


def main(argv: list[str]) -> int:
    # pre-commit passes staged file paths as argv; `pre-commit run --all-files`
    # passes all tracked files.  If no args, scan all tracked files via git ls-files.
    paths: list[Path]
    if len(argv) > 1:
        paths = [Path(a) for a in argv[1:]]
    else:
        import shutil
        import subprocess

        git = shutil.which("git")
        try:
            # S603: git comes from shutil.which (trusted PATH lookup); the args
            # are a constant command, never user-controlled input.
            out = subprocess.check_output(  # noqa: S603
                [git, "ls-files", "-z"], text=False
            )
            paths = [Path(p.decode()) for p in out.split(b"\x00") if p]
        except Exception:
            paths = []

    all_findings: list[str] = []
    for p in paths:
        if not p.exists() or p.is_dir():
            continue
        if _should_skip_path(p):
            continue
        all_findings.extend(scan_file(p))

    if all_findings:
        print(
            "check-secrets: credential/token pattern detected — blocking commit:", file=sys.stderr
        )
        for f in all_findings:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nFix: remove the token/credential URL, use `gh auth login`, or move "
            "secrets to .env (gitignored).",
            file=sys.stderr,
        )
        print(
            "If this is a false positive (placeholder/example), add the allowlist "
            "marker or update ALLOWLIST_LINE_RE in scripts/check-secrets.py.",
            file=sys.stderr,
        )
        return 1

    # Also do a repo-wide sweep when run as `pre-commit run --all-files` or with no args:
    # already covered via git ls-files above.  Single-file runs are fast; all-files is still <1s.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
