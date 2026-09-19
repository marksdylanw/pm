import os

from fastapi.testclient import TestClient

from app.main import app
from app.config import resolve_static_dir
from app.routes import static as static_module

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_html() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "PM MVP" in response.text


def test_api_hello() -> None:
    response = client.get("/api/hello")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello from FastAPI"}


def test_root_serves_static_index(tmp_path) -> None:
    original_static_dir = static_module.STATIC_DIR
    index_path = tmp_path / "index.html"
    index_path.write_text("Kanban Studio")

    static_module.STATIC_DIR = tmp_path
    response = client.get("/")
    assert response.status_code == 200
    assert "Kanban Studio" in response.text
    static_module.STATIC_DIR = original_static_dir


def test_static_fallback_serves_files(tmp_path) -> None:
    original_static_dir = static_module.STATIC_DIR
    index_path = tmp_path / "index.html"
    index_path.write_text("Index content")
    file_path = tmp_path / "hello.txt"
    file_path.write_text("Hello file")

    static_module.STATIC_DIR = tmp_path
    response = client.get("/hello.txt")
    assert response.status_code == 200
    assert response.text == "Hello file"
    static_module.STATIC_DIR = original_static_dir


def test_static_fallback_returns_index(tmp_path) -> None:
    original_static_dir = static_module.STATIC_DIR
    index_path = tmp_path / "index.html"
    index_path.write_text("Index content")

    static_module.STATIC_DIR = tmp_path
    response = client.get("/unknown/path")
    assert response.status_code == 200
    assert "Index content" in response.text
    static_module.STATIC_DIR = original_static_dir


def test_static_fallback_404_when_missing() -> None:
    original_static_dir = static_module.STATIC_DIR
    static_module.STATIC_DIR = None

    response = client.get("/missing")
    assert response.status_code == 404
    static_module.STATIC_DIR = original_static_dir


def test_resolve_static_dir_uses_env(tmp_path) -> None:
    original_env = os.environ.get("PM_STATIC_DIR")
    os.environ["PM_STATIC_DIR"] = str(tmp_path)
    try:
        resolved = resolve_static_dir()
        assert resolved == tmp_path
    finally:
        if original_env is None:
            os.environ.pop("PM_STATIC_DIR", None)
        else:
            os.environ["PM_STATIC_DIR"] = original_env


def test_mount_static_assets(tmp_path) -> None:
    from app.main import _mount_static_assets
    (tmp_path / "_next").mkdir()
    (tmp_path / "static").mkdir()
    _mount_static_assets(tmp_path)


def test_static_fallback_directory_index(tmp_path) -> None:
    original_static_dir = static_module.STATIC_DIR
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    (nested_dir / "index.html").write_text("Nested index")
    (tmp_path / "index.html").write_text("Root index")

    static_module.STATIC_DIR = tmp_path
    response = client.get("/nested")
    assert response.status_code == 200
    assert "Nested index" in response.text
    static_module.STATIC_DIR = original_static_dir


def test_static_fallback_404_without_index(tmp_path) -> None:
    original_static_dir = static_module.STATIC_DIR
    static_module.STATIC_DIR = tmp_path

    response = client.get("/no-index")
    assert response.status_code == 404
    static_module.STATIC_DIR = original_static_dir


def test_static_fallback_blocks_path_traversal(tmp_path) -> None:
    original_static_dir = static_module.STATIC_DIR
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("Index content")

    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("top secret")

    static_module.STATIC_DIR = static_dir
    response = static_module.static_fallback("../secret.txt")
    assert response.status_code == 404
    static_module.STATIC_DIR = original_static_dir
