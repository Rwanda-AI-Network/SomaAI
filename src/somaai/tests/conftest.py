"""Test configuration."""

import pytest
from fastapi.testclient import TestClient

from somaai.app import create_app


@pytest.fixture
def client():
    """Create test client."""
    from somaai.deps import get_settings
    from somaai.settings import Settings

    app = create_app()
    
    # Force mock backend for tests
    def get_test_settings():
        return Settings(llm_backend="mock")

    app.dependency_overrides[get_settings] = get_test_settings

    with TestClient(app) as c:
        yield c
