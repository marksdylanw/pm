# Backend overview

## Stack
- FastAPI
- Uvicorn
- SQLite
- Pytest for unit and integration tests

## Package Structure
```
app/
├── __init__.py
├── main.py          # FastAPI app, lifespan, route registration
├── config.py        # Environment config, constants, seed data
├── models.py        # Pydantic request/response models
├── database.py      # DB connection, init, queries
├── ai.py            # OpenRouter integration, action application
├── dependencies.py  # FastAPI dependencies (get_db, get_username)
└── routes/
    ├── __init__.py  # Router aggregation
    ├── board.py     # Board, column, card CRUD endpoints
    ├── chat.py      # Chat endpoint with AI
    └── static.py    # Static file serving
```

## Entry point
- app/main.py exposes the FastAPI application instance as `app`.

## Routes
- GET /health: JSON status
- GET /api/hello: JSON example endpoint
- GET /api/board: Fetch user's board
- POST/PATCH/DELETE /api/columns/{id}: Column CRUD (create/delete are unused by the UI and AI action schema today — columns are product-fixed/rename-only; kept as intentional API surface)
- POST/PATCH/DELETE /api/cards/{id}: Card CRUD
- POST /api/chat: AI chat with structured output
- GET /: Serves frontend or fallback HTML

CORS is enabled (see app/main.py) for http://localhost:3000 so `npm run dev` can call this backend directly during local development. Production doesn't need it since the backend serves the built frontend from the same origin.

## Tests
- Unit tests: tests/test_main.py, test_board_api.py, test_chat_api.py, test_ai_actions.py
- Integration tests (live target): tests/test_integration.py
	- Uses PM_BASE_URL to target a running backend

## Container
- Dockerfile at repo root builds a Python 3.12 image and installs dependencies with uv.
- Runs as non-root user `appuser`
- Includes HEALTHCHECK directive
