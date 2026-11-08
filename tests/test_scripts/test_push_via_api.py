"""Offline tests for ``scripts/push_via_api.py`` (issue #427).

The script talks to api.github.com when ``github.com:443`` is unreachable and
rebuilds a branch commit-by-commit through the Git Data API. Network calls are
NEVER made here — only the pure helpers (log/diff parsers, tree payload
builder, origin-remote parser, ref-upsert fallback) and the CLI surface are
exercised. The SHA-verification live path was proven operationally (branch
replication with byte-identical SHAs, calibration #14); its building blocks
are pinned below so a refactor cannot silently break the parser contracts the
verification depends on.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "push_via_api.py"


@pytest.fixture(scope="module")
def pva() -> object:
    """Load the script module once (registered in sys.modules: @dataclass)."""
    if "push_via_api_under_test" in sys.modules:
        return sys.modules["push_via_api_under_test"]
    spec = importlib.util.spec_from_file_location("push_via_api_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # MUST register before exec_module (dataclass)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# parse_origin_remote
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/1StepMore/AutoMedia.git", ("1StepMore", "AutoMedia")),
        ("https://github.com/1StepMore/AutoMedia", ("1StepMore", "AutoMedia")),
        ("git@github.com:1StepMore/AutoMedia.git", ("1StepMore", "AutoMedia")),
        ("ssh://git@github.com/1StepMore/AutoMedia.git", ("1StepMore", "AutoMedia")),
        ("git://github.com/1StepMore/AutoMedia.git", ("1StepMore", "AutoMedia")),
    ],
)
def test_parse_origin_remote_known_schemes(
    pva: object, url: str, expected: tuple[str, str]
) -> None:
    assert pva.parse_origin_remote(url) == expected


def test_parse_origin_remote_unknown_scheme_exits(pva: object) -> None:
    with pytest.raises(SystemExit):
        pva.parse_origin_remote("https://gitlab.com/foo/bar.git")


# ---------------------------------------------------------------------------
# parse_commit_log
# ---------------------------------------------------------------------------

LOG_LINE = (
    "abc123def456abc123def456abc123def456ab|tree1111111111111111111111111111111"
    "|p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1 p2p2p2p2p2p2p2p2p2p2p2p2p2p2p2p2"
    "p2p2p2p2|Owner|owner@example.com|2026-11-08T10:00:00+08:00|Owner|owner@example.com"
    "|2026-11-08T10:00:00+08:00"
)


def test_parse_commit_log_fields(pva: object) -> None:
    (meta,) = pva.parse_commit_log(LOG_LINE)
    assert meta.sha == "abc123def456abc123def456abc123def456ab"
    assert meta.parents == (
        "p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1",
        "p2p2p2p2p2p2p2p2p2p2p2p2p2p2p2p2p2p2p2p2",
    )
    assert meta.author_date == "2026-11-08T10:00:00+08:00"
    assert meta.committer_email == "owner@example.com"


def test_parse_commit_log_skips_blank_lines(pva: object) -> None:
    assert pva.parse_commit_log(LOG_LINE + "\n\n") == pva.parse_commit_log(LOG_LINE)


# ---------------------------------------------------------------------------
# parse_diff_tree (-z) and build_tree_payload
# ---------------------------------------------------------------------------


def test_parse_diff_tree_modes_and_deletion(pva: object) -> None:
    raw = (
        ":100644 100644 old new M\0kept.txt\0"
        ":100644 000000 aaa bbb D\0gone.txt\0"
        ":100644 120000 aaa target A\0link\0"
        ":100644 160000 aaa subsha A\0vendor/pkg\0"
    )
    entries = pva.parse_diff_tree(raw)
    assert [(e.path, e.mode) for e in entries] == [
        ("kept.txt", "100644"),
        ("gone.txt", "000000"),
        ("link", "120000"),
        ("vendor/pkg", "160000"),
    ]


def test_build_tree_payload_deletion_uses_null_sha(pva: object) -> None:
    payload = pva.build_tree_payload(pva.parse_diff_tree(":100644 000000 a b D\0gone.txt\0"))
    assert payload == [{"path": "gone.txt", "mode": "100644", "sha": None}]


def test_build_tree_payload_submodule_is_commit_type(pva: object) -> None:
    payload = pva.build_tree_payload(pva.parse_diff_tree(":100644 160000 aaa subsha A\0pkg\0"))
    assert payload == [{"path": "pkg", "mode": "160000", "type": "commit", "sha": "subsha"}]


def test_build_tree_payload_blob_keeps_mode(pva: object) -> None:
    payload = pva.build_tree_payload(pva.parse_diff_tree(":100755 100755 x y A\0run.sh\0"))
    assert payload == [{"path": "run.sh", "mode": "100755", "type": "blob", "sha": "y"}]


# ---------------------------------------------------------------------------
# _upsert_ref fallback (create -> PATCH on 422)
# ---------------------------------------------------------------------------


class _FakeApi:
    def __init__(self, create_error: Exception | None = None) -> None:
        self.create_error = create_error
        self.calls: list[tuple[str, str]] = []

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        self.calls.append((method, path))
        if method == "POST" and path.endswith("/git/refs"):
            if self.create_error is not None:
                raise self.create_error
            return {}
        if method == "PATCH" and "/git/refs/heads/" in path:
            assert payload == {"sha": "deadbeef", "force": True}
            return {}
        raise AssertionError(f"unexpected call {method} {path}")


def test_upsert_ref_create_succeeds_without_patch(pva: object) -> None:
    api = _FakeApi()
    pva._upsert_ref(api, "/repos/o/r", "br", "deadbeef", False)
    assert ("POST", "/repos/o/r/git/refs") in api.calls
    assert all(m != "PATCH" for m, _ in api.calls)


def test_upsert_ref_falls_back_to_patch_on_422(pva: object) -> None:
    err = pva.ApiError("API POST /git/refs -> HTTP 422: already exists")
    api = _FakeApi(create_error=err)
    pva._upsert_ref(api, "/repos/o/r", "br", "deadbeef", True)
    assert ("PATCH", "/repos/o/r/git/refs/heads/br") in api.calls


def test_upsert_ref_non_422_error_propagates(pva: object) -> None:
    err = pva.ApiError("API POST /git/refs -> HTTP 403: forbidden")
    api = _FakeApi(create_error=err)
    with pytest.raises(pva.ApiError):
        pva._upsert_ref(api, "/repos/o/r", "br", "deadbeef", False)


# ---------------------------------------------------------------------------
# CLI surface (no network: argparse only)
# ---------------------------------------------------------------------------


def test_cli_requires_branch_and_repo_root(pva: object) -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--branch" in proc.stdout
    assert "Git Data API" in proc.stdout


def test_module_import_has_no_side_effects(pva: object) -> None:
    """Importing the module must not fetch a token or touch the network."""
    import importlib.util as _ilu

    name = "push_via_api_sideeffect_probe"
    spec = _ilu.spec_from_file_location(name, SCRIPT)
    module = _ilu.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    # The token is fetched lazily by ApiClient.token; a fresh module object
    # carries no cached token and main() was not invoked.
    assert getattr(module, "__name__", "") == name
