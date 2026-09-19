import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.database import (
    clamp_position,
    fetch_board,
    get_or_create_board,
    get_or_create_user,
    ordered_ids,
    resequence_positions,
)
from app.dependencies import get_db, get_username
from app.models import CardCreate, CardUpdate, ColumnCreate, ColumnUpdate

router = APIRouter()


@router.get("/api/board")
def get_board(
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    return fetch_board(conn, user_id)


@router.post("/api/columns")
def create_column(
    payload: ColumnCreate,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    # Note: the current UI treats columns as fixed (rename-only) and the AI
    # action schema has no create/delete-column action, so this route (and
    # delete_column below) is only reachable via a direct API call today.
    # Kept as intentional future-facing API surface rather than removed.
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    columns = conn.execute(
        "SELECT id FROM columns WHERE board_id = ? ORDER BY position",
        (board_id,),
    ).fetchall()
    ids = ordered_ids(columns)

    insert_position = clamp_position(payload.position, len(ids))

    cursor = conn.execute(
        "INSERT INTO columns (board_id, title, position) VALUES (?, ?, ?)",
        (board_id, payload.title, insert_position),
    )
    column_id = int(cursor.lastrowid)
    ids.insert(insert_position, column_id)
    resequence_positions(conn, "columns", ids, "AND board_id = ?", (board_id,))
    conn.commit()

    return {"id": str(column_id)}


@router.patch("/api/columns/{column_id}")
def update_column(
    column_id: int,
    payload: ColumnUpdate,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    column = conn.execute(
        "SELECT id FROM columns WHERE id = ? AND board_id = ?",
        (column_id, board_id),
    ).fetchone()
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")

    if payload.title is not None:
        conn.execute(
            "UPDATE columns SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (payload.title, column_id),
        )

    if payload.position is not None:
        columns = conn.execute(
            "SELECT id FROM columns WHERE board_id = ? ORDER BY position",
            (board_id,),
        ).fetchall()
        ids = ordered_ids(columns)
        if column_id in ids:
            ids.remove(column_id)
        insert_position = clamp_position(payload.position, len(ids))
        ids.insert(insert_position, column_id)
        resequence_positions(conn, "columns", ids, "AND board_id = ?", (board_id,))

    conn.commit()
    return {"status": "ok"}


# See note on create_column above re: intentional unused-by-UI surface.
@router.delete("/api/columns/{column_id}")
def delete_column(
    column_id: int,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    column = conn.execute(
        "SELECT id FROM columns WHERE id = ? AND board_id = ?",
        (column_id, board_id),
    ).fetchone()
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")

    conn.execute("DELETE FROM cards WHERE column_id = ?", (column_id,))
    conn.execute("DELETE FROM columns WHERE id = ?", (column_id,))

    remaining = conn.execute(
        "SELECT id FROM columns WHERE board_id = ? ORDER BY position",
        (board_id,),
    ).fetchall()
    resequence_positions(conn, "columns", ordered_ids(remaining), "AND board_id = ?", (board_id,))
    conn.commit()

    return {"status": "ok"}


@router.post("/api/cards")
def create_card(
    payload: CardCreate,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    column = conn.execute(
        "SELECT id FROM columns WHERE id = ? AND board_id = ?",
        (payload.column_id, board_id),
    ).fetchone()
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")

    cards = conn.execute(
        "SELECT id FROM cards WHERE column_id = ? AND archived = 0 ORDER BY position",
        (payload.column_id,),
    ).fetchall()
    ids = ordered_ids(cards)

    insert_position = clamp_position(payload.position, len(ids))

    cursor = conn.execute(
        "INSERT INTO cards (column_id, title, details, position) VALUES (?, ?, ?, ?)",
        (payload.column_id, payload.title, payload.details, insert_position),
    )
    card_id = int(cursor.lastrowid)
    ids.insert(insert_position, card_id)
    resequence_positions(conn, "cards", ids, "AND column_id = ?", (payload.column_id,))
    conn.commit()

    return {"id": str(card_id)}


@router.patch("/api/cards/{card_id}")
def update_card(
    card_id: int,
    payload: CardUpdate,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    card = conn.execute(
        """
        SELECT cards.id, cards.column_id
        FROM cards
        JOIN columns ON cards.column_id = columns.id
        WHERE cards.id = ? AND columns.board_id = ?
        """,
        (card_id, board_id),
    ).fetchone()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    if payload.title is not None:
        conn.execute(
            "UPDATE cards SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (payload.title, card_id),
        )
    if payload.details is not None:
        conn.execute(
            "UPDATE cards SET details = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (payload.details, card_id),
        )

    current_column_id = int(card["column_id"])
    target_column_id = payload.column_id or current_column_id

    if payload.column_id is not None:
        column = conn.execute(
            "SELECT id FROM columns WHERE id = ? AND board_id = ?",
            (payload.column_id, board_id),
        ).fetchone()
        if not column:
            raise HTTPException(status_code=404, detail="Column not found")

    if payload.position is not None or target_column_id != current_column_id:
        source_cards = conn.execute(
            "SELECT id FROM cards WHERE column_id = ? AND archived = 0 ORDER BY position",
            (current_column_id,),
        ).fetchall()
        source_ids = ordered_ids(source_cards)
        if card_id in source_ids:
            source_ids.remove(card_id)

        target_cards = conn.execute(
            "SELECT id FROM cards WHERE column_id = ? AND archived = 0 ORDER BY position",
            (target_column_id,),
        ).fetchall()
        target_ids = ordered_ids(target_cards)

        insert_position = clamp_position(payload.position, len(target_ids))

        target_ids.insert(insert_position, card_id)

        conn.execute(
            "UPDATE cards SET column_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (target_column_id, card_id),
        )
        resequence_positions(conn, "cards", source_ids, "AND column_id = ?", (current_column_id,))
        resequence_positions(conn, "cards", target_ids, "AND column_id = ?", (target_column_id,))

    conn.commit()
    return {"status": "ok"}


@router.delete("/api/cards/{card_id}")
def delete_card(
    card_id: int,
    username: str = Depends(get_username),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    user_id = get_or_create_user(conn, username)
    board_id = get_or_create_board(conn, user_id)

    card = conn.execute(
        """
        SELECT cards.id, cards.column_id
        FROM cards
        JOIN columns ON cards.column_id = columns.id
        WHERE cards.id = ? AND columns.board_id = ?
        """,
        (card_id, board_id),
    ).fetchone()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    column_id = int(card["column_id"])
    conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    remaining = conn.execute(
        "SELECT id FROM cards WHERE column_id = ? AND archived = 0 ORDER BY position",
        (column_id,),
    ).fetchall()
    resequence_positions(conn, "cards", ordered_ids(remaining), "AND column_id = ?", (column_id,))
    conn.commit()
    return {"status": "ok"}
