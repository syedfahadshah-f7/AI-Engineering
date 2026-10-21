from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_config_never_exposes_api_key():
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.text.lower()
    assert "api_key" not in body and "sk-" not in body
    assert len(r.json()["models"]) == 4


def test_geometry_has_54_stickers():
    data = client.get("/api/cube/geometry").json()
    assert len(data["stickers"]) == 54


def test_preview_and_bad_test_set():
    p = client.get("/api/puzzles/preview", params={"test_set": "primary", "seed": 2}).json()
    assert p["optimal_exact"]
    assert client.get("/api/puzzles/preview", params={"test_set": "nope"}).status_code == 400
    assert client.post("/api/sessions", json={"test_set": "nope"}).status_code == 422
