from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db


def _make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PM_DB_PATH", str(tmp_path / "test.db"))
    init_db()
    return TestClient(app)


def test_get_board_returns_seeded_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(tmp_path, monkeypatch)
    response = client.get("/api/board")
    assert response.status_code == 200
    data = response.json()
    assert len(data["columns"]) == 5
    assert len(data["cards"]) >= 8


def test_create_and_rename_column(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(tmp_path, monkeypatch)
    create = client.post("/api/columns", json={"title": "New Column"})
    assert create.status_code == 200
    column_id = create.json()["id"]

    rename = client.patch(f"/api/columns/{column_id}", json={"title": "Renamed"})
    assert rename.status_code == 200

    board = client.get("/api/board").json()
    titles = [column["title"] for column in board["columns"]]
    assert "Renamed" in titles


def test_create_move_and_delete_card(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(tmp_path, monkeypatch)
    board = client.get("/api/board").json()
    first_column = board["columns"][0]
    second_column = board["columns"][1]

    create = client.post(
        "/api/cards",
        json={
            "column_id": int(first_column["id"]),
            "title": "New Card",
            "details": "Details",
        },
    )
    assert create.status_code == 200
    card_id = create.json()["id"]

    move = client.patch(
        f"/api/cards/{card_id}",
        json={"column_id": int(second_column["id"]), "position": 0},
    )
    assert move.status_code == 200

    updated = client.get("/api/board").json()
    assert card_id in updated["columns"][1]["cardIds"]

    delete = client.delete(f"/api/cards/{card_id}")
    assert delete.status_code == 200

    final = client.get("/api/board").json()
    assert card_id not in final["cards"]


def test_delete_column_removes_cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(tmp_path, monkeypatch)
    board = client.get("/api/board").json()
    target_column = board["columns"][0]
    column_id = target_column["id"]
    card_ids = list(target_column["cardIds"])

    delete = client.delete(f"/api/columns/{column_id}")
    assert delete.status_code == 200

    updated = client.get("/api/board").json()
    assert column_id not in {column["id"] for column in updated["columns"]}
    for card_id in card_ids:
        assert card_id not in updated["cards"]
