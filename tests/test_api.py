import os
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_get_tasa_bcv():
    r = client.get("/tasa-bcv/")
    assert r.status_code == 200
    data = r.json()
    assert "tasa_bcv" in data
    assert "origen" in data
    assert "es_fallback" in data


def test_convertir_a_usd():
    payload = {"monto_bs": 10000}
    r = client.post("/convertir-a-usd/", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["monto_bs"] == 10000.0
    assert data["monto_usd"] >= 0.0
    assert "tasa_bcv" in data
    assert "origen" in data


@pytest.mark.skipif(not os.getenv("API_KEY"), reason="API_KEY no configurado en .env")
def test_set_tasa_bcv_with_api_key():
    api_key = os.getenv("API_KEY")
    payload = {"tasa_bcv": 123.45}
    r = client.post("/tasa-bcv/", json=payload, headers={"x-api-key": api_key})
    assert r.status_code == 200
    data = r.json()
    assert data["tasa_bcv"] == 123.45
    r2 = client.get("/tasa-bcv/")
    assert r2.status_code == 200
    tasa_recibida = float(r2.json()["tasa_bcv"])
    assert tasa_recibida > 0
    assert r2.json().get("origen") in {"API", "SCRAPING", "DB", "ENV"}
