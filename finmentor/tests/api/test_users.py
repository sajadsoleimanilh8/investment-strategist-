"""POST /api/users and GET /api/users/{id} against the test database."""
from app.repositories import users as users_repo


def test_create_user_persists_and_returns_it(client, db):
    response = client.post("/api/users", json={"telegram_id": 555_001, "locale": "fa"})

    assert response.status_code == 201
    body = response.json()
    assert body["telegram_id"] == 555_001
    assert body["locale"] == "fa"
    assert body["risk_profile"] is None
    assert body["id"] > 0

    assert users_repo.get_by_telegram_id(db, 555_001).id == body["id"]


def test_created_user_is_readable_back(client):
    created = client.post("/api/users", json={"telegram_id": 555_002}).json()

    response = client.get(f"/api/users/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_locale_defaults_to_persian(client):
    body = client.post("/api/users", json={"telegram_id": 555_003}).json()
    assert body["locale"] == "fa"


def test_duplicate_telegram_id_is_rejected(client):
    client.post("/api/users", json={"telegram_id": 555_004})
    response = client.post("/api/users", json={"telegram_id": 555_004})

    assert response.status_code == 409
    assert "telegram_id" in response.json()["detail"]


def test_unknown_user_is_404(client):
    response = client.get("/api/users/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "user not found"


def test_invalid_payloads_are_422(client):
    assert client.post("/api/users", json={}).status_code == 422
    assert client.post("/api/users", json={"telegram_id": "abc"}).status_code == 422
    assert client.post("/api/users", json={"telegram_id": -1}).status_code == 422


def test_user_endpoints_are_documented(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/users"]
    assert "get" in paths["/api/users/{user_id}"]
