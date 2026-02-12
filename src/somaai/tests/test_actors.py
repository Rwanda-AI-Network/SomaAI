from fastapi.testclient import TestClient


def test_create_anonymous_actor(client: TestClient):
    """Test creating an anonymous actor ID."""
    response = client.post("/api/v1/actors/anonymous")
    assert response.status_code == 200
    data = response.json()
    assert "actor_id" in data
    assert isinstance(data["actor_id"], str)
    assert len(data["actor_id"]) > 0
