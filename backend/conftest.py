"""Pytest bootstrap: make backend/ importable and share one API client."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import dataset  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    import main  # noqa: WPS433

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def provenance() -> dict:
    return dataset.warehouse().provenance
