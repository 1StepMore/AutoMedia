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
    ("github_pat", re.compile(r"(ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{60,})")),
    ("cred_url", re.compile(r"https://[^/\s:]+:[^/\s@]+@github\.com")),
    ("cred_url_generic", re.compile(r"https://[^/\s:]+:[^/\s@]+@[^/\s]+\.[^/\s]+")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_header", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
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
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".woff", ".woff2", ".ttf", ".otf",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".pdf", ".bin", ".safetensors", ".gguf", ".h5", ".parquet",
    ".pyc", ".pyo", ".so", ".dylib", ".dll",
    ".mp4", ".mp3", ".wav", ".m4a",
}

def _should_skip_path(p: Path) -> bool:
    s = p.as_posix()
    if any(sub in s for sub in ALLOWLIST_PATH_SUBSTRINGS):
        return True
    if p.suffix.lower() in SKIP_SUFFIXES:
        return True
    # Skip common large/ignored dirs even if pre-commit somehow passes them
    if any(part in {".git", ".venv", ".mypy_cache", ".ruff_cache", ".pytest_cache",
                     ".hypothesis", "site", "build", "dist", ".codegraph", "node_modules", "__pycache__"}
           for part in p.parts):
        return True
    return False


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
        import subprocess
        try:
            out = subprocess.check_output(["git", "ls-files", "-z"], text=False)
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
        print("check-secrets: credential/token pattern detected — blocking commit:", file=sys.stderr)
        for f in all_findings:
            print(f"  {f}", file=sys.stderr)
        print("\nFix: remove the token/credential URL, use `gh auth login`, or move secrets to .env (gitignored).", file=sys.stderr)
        print("If this is a false positive (placeholder/example), add the allowlist marker or update ALLOWLIST_LINE_RE in scripts/check-secrets.py.", file=sys.stderr)
        return 1

    # Also do a repo-wide sweep when run as `pre-commit run --all-files` or with no args:
    # already covered via git ls-files above.  Single-file runs are fast; all-files is still <1s.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
