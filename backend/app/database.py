import sqlite3
from typing import Iterable, Literal

from app.config import DEFAULT_BOARD_TITLE, INITIAL_COLUMNS, get_db_path

VALID_TABLES = {"cards", "columns"}


def connect_db() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = connect_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS boards (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT 'My Board',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE (user_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS columns (
            id INTEGER PRIMARY KEY,
            board_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            position INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (board_id) REFERENCES boards(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY,
            column_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (column_id) REFERENCES columns(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_boards_user_id ON boards(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_columns_board_id ON columns(board_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_column_id ON cards(column_id)")
    conn.commit()
    conn.close()


def get_or_create_user(conn: sqlite3.Connection, username: str) -> int:
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        return int(row["id"])
    cursor = conn.execute("INSERT INTO users (username) VALUES (?)", (username,))
    conn.commit()
    return int(cursor.lastrowid)


def get_or_create_board(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute("SELECT id FROM boards WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return int(row["id"])
    cursor = conn.execute(
        "INSERT INTO boards (user_id, title) VALUES (?, ?)",
        (user_id, DEFAULT_BOARD_TITLE),
    )
    conn.commit()
    return int(cursor.lastrowid)


def ensure_seed_data(conn: sqlite3.Connection, user_id: int) -> int:
    board_id = get_or_create_board(conn, user_id)
    column_count = conn.execute(
        "SELECT COUNT(*) AS count FROM columns WHERE board_id = ?",
        (board_id,),
    ).fetchone()["count"]
    if column_count:
        return board_id

    for column_index, (column_title, cards) in enumerate(INITIAL_COLUMNS):
        column_cursor = conn.execute(
            "INSERT INTO columns (board_id, title, position) VALUES (?, ?, ?)",
            (board_id, column_title, column_index),
        )
        column_id = int(column_cursor.lastrowid)
        for card_index, (title, details) in enumerate(cards):
            conn.execute(
                "INSERT INTO cards (column_id, title, details, position) VALUES (?, ?, ?, ?)",
                (column_id, title, details, card_index),
            )
    conn.commit()
    return board_id


def fetch_board(conn: sqlite3.Connection, user_id: int) -> dict:
    board_id = ensure_seed_data(conn, user_id)
    board_row = conn.execute(
        "SELECT id, title FROM boards WHERE id = ?",
        (board_id,),
    ).fetchone()

    column_rows = conn.execute(
        "SELECT id, title, position FROM columns WHERE board_id = ? ORDER BY position",
        (board_id,),
    ).fetchall()

    card_rows = conn.execute(
        """
        SELECT id, column_id, title, details, position
        FROM cards
        WHERE archived = 0 AND column_id IN (
            SELECT id FROM columns WHERE board_id = ?
        )
        ORDER BY column_id, position
        """,
        (board_id,),
    ).fetchall()

    cards_by_id = {
        str(row["id"]): {
            "id": str(row["id"]),
            "title": row["title"],
            "details": row["details"],
        }
        for row in card_rows
    }

    cards_by_column: dict[int, list[str]] = {int(row["id"]): [] for row in column_rows}
    for row in card_rows:
        cards_by_column[int(row["column_id"])].append(str(row["id"]))

    columns_payload = [
        {
            "id": str(row["id"]),
            "title": row["title"],
            "position": row["position"],
            "cardIds": cards_by_column.get(int(row["id"]), []),
        }
        for row in column_rows
    ]

    return {
        "board": {"id": str(board_row["id"]), "title": board_row["title"]},
        "columns": columns_payload,
        "cards": cards_by_id,
    }


def ordered_ids(rows: Iterable[sqlite3.Row]) -> list[int]:
    return [int(row["id"]) for row in rows]


def clamp_position(position: int | None, upper_bound: int) -> int:
    if position is None or position > upper_bound:
        return upper_bound
    return max(position, 0)


def resequence_positions(
    conn: sqlite3.Connection,
    table: Literal["cards", "columns"],
    ids: list[int],
    extra_where: str,
    extra_params: tuple,
) -> None:
    if table not in VALID_TABLES:
        raise ValueError(f"Invalid table: {table}")
    for index, item_id in enumerate(ids):
        conn.execute(
            f"UPDATE {table} SET position = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? {extra_where}",
            (index, item_id, *extra_params),
        )
