"""Pytest configuration and fixtures for MapToPrint tests."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    from web.app import app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_preview_request():
    """Sample preview request data."""
    return {
        "city": "Prague",
        "country": "Czech Republic",
        "theme": "noir",
        "distance": 5000,
        "width": 12,
        "height": 16,
        "features": {
            "water": True,
            "parks": True,
            "roads_drive": True,
            "roads_paths": True,
            "roads_cycling": True,
            "roads": True,
            "paths": False
        }
    }
