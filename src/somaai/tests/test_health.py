"""Health endpoint tests."""


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "components" in data
    assert data["components"]["database"] == "healthy"
    assert data["components"]["qdrant"] == "healthy"
