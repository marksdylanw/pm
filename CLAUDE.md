# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Project Management MVP web app with a Kanban board and AI chat assistant. Users sign in, view/manage a Kanban board with drag-and-drop, and interact with an AI that can create/edit/move cards.

**Stack:** Next.js 16 frontend (React 19, TypeScript, Tailwind v4, @dnd-kit) + Python FastAPI backend + SQLite database, all packaged in Docker. AI via OpenRouter using `openai/gpt-oss-120b`.

**MVP constraints:** Hardcoded login (`user`/`password`), one board per user, local Docker deployment only.

## Commands

### Running the app (Docker)
```bash
# Mac
scripts/start-mac.sh    # Start
scripts/stop-mac.sh     # Stop

# Linux
scripts/start-linux.sh
scripts/stop-linux.sh

# Windows
scripts/start-windows.ps1
scripts/stop-windows.ps1
```
Backend available at http://localhost:8000

### Frontend (from `frontend/` directory)
```bash
npm run dev           # Dev server
npm run build         # Build static export
npm run lint          # ESLint
npm run test:unit     # Vitest unit tests
npm run test:e2e      # Playwright E2E tests
npm run test:all      # All tests
```

### Backend (from `backend/` directory)
```bash
pytest                           # Run all tests
pytest tests/test_main.py        # Single test file
pytest -k "test_name"            # Single test by name
PM_BASE_URL=http://localhost:8000 pytest tests/test_integration.py  # Integration tests against running server
```

## Architecture

**Frontend (`frontend/src/`):**
- `app/page.tsx` - Main page: login screen, loads board from `/api/board` after sign-in, owns chat history
- `components/KanbanBoard.tsx` - Board state owner, drag-and-drop handling (DndContext + DragOverlay)
- `components/KanbanColumn.tsx` / `KanbanCard.tsx` / `KanbanCardPreview.tsx` / `NewCardForm.tsx` - Column/card rendering, inline edit forms, drag overlay preview
- `components/ChatSidebar.tsx` - AI chat interface; applies board updates returned by the AI immediately
- `lib/api.ts` - API client functions (fetchBoard, createCard, updateCard, deleteCard, updateColumn, sendChat); sends `X-User` header
- `lib/kanban.ts` - Data types (Card, Column, BoardData), `moveCard`/`findCardLocation`, and the `toColumnId`/`toCardId`/`fromColumnId`/`fromCardId` prefix helpers
- Full details in `frontend/AGENTS.md`.

**Backend (`backend/app/`):** modular FastAPI app (see `backend/AGENTS.md` for the full layout)
- `main.py` - App instance, lifespan, route registration
- `config.py` - Environment config, constants, seed data
- `models.py` - Pydantic request/response models
- `database.py` - SQLite connection, init, queries (tables: users, boards, columns, cards)
- `ai.py` - OpenRouter integration and AI action application
- `dependencies.py` - FastAPI dependencies (`get_db`, `get_username`)
- `routes/board.py`, `routes/chat.py`, `routes/static.py` - Board/column/card CRUD, AI chat, and static frontend serving
- Key routes: `/api/board` (GET), `/api/columns/{id}` (CRUD), `/api/cards/{id}` (CRUD), `/api/chat` (AI), `/` (serves built frontend)

**ID Prefixing:** Frontend prefixes IDs with `col-` and `card-` for drag-and-drop stability, strips them for API calls.

Root `AGENTS.md` (and the per-directory `frontend/AGENTS.md`, `backend/AGENTS.md`, `scripts/AGENTS.md`) hold the authoritative, more detailed architecture notes — check them when this section and the code disagree.

## Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)
- Dark Navy: `#032147` (headings)
- Gray Text: `#888888`

## Development Guidelines

- Keep it simple. No over-engineering or unnecessary defensive programming.
- Identify root cause before fixing issues. Prove with evidence, then fix.
- Work incrementally with small steps. Validate each increment.
- Use latest library APIs.
- Use `uv` as Python package manager in Docker.
- Planning docs are in `docs/` - review `docs/PLAN.md` for context.


## DETAILED PLAN

@docs/PLAN.md

