"""Shared test fixtures for the accounts subsystem.

All fixtures produce synthetic data only — zero real credentials or
production data.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from automedia.accounts.store import AccountStore

# Test master key — used by all store tests.
# Intentionally simple; real deployments should use a strong, unique key.
TEST_MASTER_KEY = "testing-key-32-bytes-long!!!"


@pytest.fixture
def temp_store_dir() -> Iterator[Path]:
    """Create a temporary directory for the account store.

    The directory is cleaned up after each test.
    """
    tmp_dir = Path(tempfile.mkdtemp())
    yield tmp_dir
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def account_store(temp_store_dir: Path) -> AccountStore:
    """Create an AccountStore with the test master key and temp directory."""
    return AccountStore(store_dir=str(temp_store_dir), master_key=TEST_MASTER_KEY)
