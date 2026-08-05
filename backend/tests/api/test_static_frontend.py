from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.main import SpaStaticFiles


def test_operations_deep_link_serves_the_single_page_app(tmp_path):
    (tmp_path / "index.html").write_text("<title>GridScope</title>")
    app = FastAPI()
    app.mount("/", SpaStaticFiles(directory=tmp_path, html=True), name="frontend")

    response = TestClient(app).get("/operations")

    assert response.status_code == 200
    assert "GridScope" in response.text


@pytest.mark.parametrize("path", ("/api", "/api/missing"))
def test_missing_api_paths_never_fall_back_to_the_single_page_app(tmp_path, path):
    (tmp_path / "index.html").write_text("<title>GridScope</title>")
    app = FastAPI()
    app.mount("/", SpaStaticFiles(directory=tmp_path, html=True), name="frontend")

    assert TestClient(app).get(path).status_code == 404
