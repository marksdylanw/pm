import json
import sqlite3

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import (
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    OPENROUTER_TEMPERATURE,
    get_openrouter_api_key,
)
from app.database import clamp_position, get_or_create_board, ordered_ids, resequence_positions
from app.models import (
    ChatHistoryItem,
    CreateCardAction,
    DeleteCardAction,
    MoveCardAction,
    StructuredChatOutput,
    UpdateCardAction,
    ChatAction,
)


def parse_structured_output(content: str) -> StructuredChatOutput:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        trimmed = content.strip()
        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(trimmed[start : end + 1])
            except json.JSONDecodeError as inner_exc:
                raise HTTPException(
                    status_code=502, detail="OpenRouter returned invalid JSON"
                ) from inner_exc
        else:
            raise HTTPException(status_code=502, detail="OpenRouter returned invalid JSON") from exc
    try:
        return StructuredChatOutput.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="OpenRouter returned invalid JSON") from exc


def call_openrouter(messages: list[dict[str, str]]) -> tuple[str, str | None]:
    api_key = get_openrouter_api_key()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not configured")

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": OPENROUTER_TEMPERATURE,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=20,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="OpenRouter request failed") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="OpenRouter returned an error")

    data = response.json()
    choices = data.get("choices", [])
    if not choices:
        raise HTTPException(status_code=502, detail="OpenRouter response missing choices")
    message_data = choices[0].get("message")
    if not message_data or "content" not in message_data:
        raise HTTPException(status_code=502, detail="OpenRouter response missing content")
    return str(message_data["content"]).strip(), data.get("model")


def build_structured_messages(
    board: dict, history: list[ChatHistoryItem], message: str
) -> list[dict[str, str]]:
    summary_parts = []
    column_titles = []
    columns = board.get("columns", [])
    cards = board.get("cards", {})
    for column in columns:
        column_titles.append(str(column.get("title")))
        card_titles = [
            cards[card_id]["title"]
            for card_id in column.get("cardIds", [])
            if card_id in cards
        ]
        summary_parts.append(
            f"{column.get('title')}: {', '.join(card_titles) if card_titles else 'No cards'}"
        )
    board_summary = " | ".join(summary_parts)
    column_summary = ", ".join(column_titles)
    schema_hint = (
        "You are a Kanban assistant. Reply only as JSON with this shape:\n"
        '{"reply": string, "actions": [action, ...]}\n'
        "Keep replies concise (1-2 sentences) unless the user requests detail.\n"
        "Board data is ALWAYS provided below. Never claim you lack board data.\n"
        "If asked to summarize the project or board, use ONLY the provided board data.\n"
        "List the columns exactly as provided and mention a few key cards. Do not invent columns or cards.\n"
        "Action types:\n"
        '- create_card: {"type": "create_card", "columnId": string, "title": string, '
        '"details": string, "position": number|null}\n'
        '- update_card: {"type": "update_card", "cardId": string, "title": string|null, '
        '"details": string|null}\n'
        '- move_card: {"type": "move_card", "cardId": string, "columnId": string, '
        '"position": number|null}\n'
        '- delete_card: {"type": "delete_card", "cardId": string}\n'
        "Do not include any extra keys or text.\n\n"
        f"Board columns (authoritative): {column_summary}\n"
        f"Board summary (authoritative): {board_summary}\n"
        f"Current board data (JSON):\n{json.dumps(board, indent=2)}"
    )
    messages_list = [{"role": "system", "content": schema_hint}]
    for item in history:
        messages_list.append({"role": item.role, "content": item.content})
    messages_list.append({"role": "user", "content": message})
    return messages_list


def apply_actions(
    conn: sqlite3.Connection, user_id: int, actions: list[ChatAction]
) -> None:
    board_id = get_or_create_board(conn, user_id)

    for action in actions:
        # The model can hallucinate non-numeric ids (e.g. echo back a
        # frontend-style "card-3" instead of "3"); skip the action instead of
        # raising an unhandled 500.
        try:
            if isinstance(action, CreateCardAction):
                column_id = int(action.columnId)
            elif isinstance(action, (UpdateCardAction, DeleteCardAction)):
                card_id = int(action.cardId)
            elif isinstance(action, MoveCardAction):
                card_id = int(action.cardId)
                target_column_id = int(action.columnId)
            else:
                continue
        except (TypeError, ValueError):
            continue

        if isinstance(action, CreateCardAction):
            column = conn.execute(
                "SELECT id FROM columns WHERE id = ? AND board_id = ?",
                (column_id, board_id),
            ).fetchone()
            if not column:
                continue

            cards = conn.execute(
                "SELECT id FROM cards WHERE column_id = ? AND archived = 0 ORDER BY position",
                (column_id,),
            ).fetchall()
            ids = ordered_ids(cards)

            insert_position = clamp_position(action.position, len(ids))

            cursor = conn.execute(
                "INSERT INTO cards (column_id, title, details, position) VALUES (?, ?, ?, ?)",
                (column_id, action.title, action.details, insert_position),
            )
            new_card_id = int(cursor.lastrowid)
            ids.insert(insert_position, new_card_id)
            resequence_positions(conn, "cards", ids, "AND column_id = ?", (column_id,))
            continue

        if isinstance(action, UpdateCardAction):
            card_row = conn.execute(
                """
                SELECT cards.id
                FROM cards
                JOIN columns ON cards.column_id = columns.id
                WHERE cards.id = ? AND columns.board_id = ?
                """,
                (card_id, board_id),
            ).fetchone()
            if not card_row:
                continue
            if action.title is not None:
                conn.execute(
                    "UPDATE cards SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (action.title, card_id),
                )
            if action.details is not None:
                conn.execute(
                    "UPDATE cards SET details = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (action.details, card_id),
                )
            continue

        if isinstance(action, MoveCardAction):
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
                continue

            target_column = conn.execute(
                "SELECT id FROM columns WHERE id = ? AND board_id = ?",
                (target_column_id, board_id),
            ).fetchone()
            if not target_column:
                continue

            current_column_id = int(card["column_id"])

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

            insert_position = clamp_position(action.position, len(target_ids))
            target_ids.insert(insert_position, card_id)

            conn.execute(
                "UPDATE cards SET column_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (target_column_id, card_id),
            )
            resequence_positions(conn, "cards", source_ids, "AND column_id = ?", (current_column_id,))
            resequence_positions(conn, "cards", target_ids, "AND column_id = ?", (target_column_id,))
            continue

        if isinstance(action, DeleteCardAction):
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
                continue
            column_id = int(card["column_id"])
            conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
            remaining = conn.execute(
                "SELECT id FROM cards WHERE column_id = ? AND archived = 0 ORDER BY position",
                (column_id,),
            ).fetchall()
            resequence_positions(conn, "cards", ordered_ids(remaining), "AND column_id = ?", (column_id,))

    conn.commit()
