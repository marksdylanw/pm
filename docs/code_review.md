# Code review

Date: 2026-09-19
Scope: full repository — backend (`backend/app/**`), frontend (`frontend/src/**`, `frontend/tests/**`), Docker/scripts, and docs. Read every non-generated source file directly (no diff-only review). All 10 parts of `docs/PLAN.md` are complete; this review looks for defects and cleanup opportunities in the finished MVP, not missing features.

Each finding lists severity, location, evidence, and a concrete action. Severity reflects impact within this project's stated MVP constraints (local-only Docker deployment, single hardcoded user) — a couple of items are called out as high severity for *any deployment beyond that*, even though they're arguably acceptable for the MVP as scoped.

**Update (2026-09-19):** all findings except #2 have been fixed and verified (backend unit + integration tests, frontend unit + Playwright E2E, all passing against a rebuilt Docker image; the path-traversal fix was also manually confirmed against the running container). #2 was deliberately left as-is — see its entry for why.

## High

### 1. Path traversal in the static-file fallback route
**File:** `backend/app/routes/static.py:42-60` (`static_fallback`)

```python
requested_path = STATIC_DIR / full_path
...
if requested_path.exists():
    return FileResponse(requested_path)
```

`full_path` comes straight from the URL (`/{full_path:path}`) and is joined onto `STATIC_DIR` with no normalization or containment check. `pathlib`'s `/` operator does not collapse `..` segments, and `Path.exists()`/`FileResponse` will happily resolve them at the OS level. A request whose path contains encoded `..` segments (bypassing client-side URL normalization) can escape `STATIC_DIR` and read arbitrary files readable by the `appuser` container user (source under `/app/backend`, etc.).

None of the existing tests in `backend/tests/test_main.py` exercise a traversal payload — all fixtures use benign relative paths (`/hello.txt`, `/nested`, `/unknown/path`).

**Action:** resolve both paths and verify containment before serving:
```python
resolved = (STATIC_DIR / full_path).resolve()
if not resolved.is_relative_to(STATIC_DIR.resolve()):
    return HTMLResponse("Not found", status_code=404)
```
Add a regression test asserting a `..`-containing path 404s instead of leaking content.

**Status: Fixed.** `static_fallback` now resolves both paths and checks `requested_path.is_relative_to(resolved_static_dir)`, 404ing otherwise. Added `test_static_fallback_blocks_path_traversal` in `backend/tests/test_main.py`, and manually confirmed `curl http://127.0.0.1:8000/..%2f..%2f..%2f..%2fetc%2fpasswd` returns 404 against the running container while `/api/board` still returns 200.

### 2. No real server-side authentication
**Files:** `backend/app/dependencies.py:18-19` (`get_username`), `frontend/src/app/page.tsx:63-78` (`handleLogin`)

Login is entirely a client-side check: `handleLogin` compares the typed username/password against a hardcoded constant in the frontend bundle and never sends credentials to the backend. Every API call then sends whatever `username` the frontend happens to hold via the `X-User` header, and `get_username()` trusts it unconditionally — `get_or_create_user` will silently provision a new user row for *any* string. Anyone who can reach the API directly (curl, another browser tab) can read or mutate any username's board with no credential at all.

This matches the project's documented MVP constraint ("hardcoded login ... local Docker deployment only" — `AGENTS.md`), so it's *acceptable as scoped*, but it should be called out explicitly rather than left implicit: **do not expose this container beyond localhost/a trusted network** without adding real backend-verified auth (e.g. a session cookie set by a `/api/login` endpoint that the rest of the API actually checks).

**Status: Not fixed, deliberately.** `AGENTS.md` and `CLAUDE.md` both state hardcoded, client-only login as an explicit MVP constraint, not an oversight — adding real server-side auth would go beyond what was asked for this pass and would change a documented product decision. Left as-is; flagged here so it isn't forgotten if this app is ever deployed beyond localhost.

## Medium

### 3. `onMoveCard` called from inside a `setState` updater (impure updater)
**File:** `frontend/src/components/KanbanBoard.tsx:109-116` (`handleDragEnd`)

```tsx
setBoard((prev) => {
  const nextColumns = moveCard(prev.columns, activeId, overId);
  onMoveCard?.(activeId, overId, nextColumns);   // side effect inside the updater
  return { ...prev, columns: nextColumns };
});
```
`onMoveCard` triggers the network `PATCH /api/cards/{id}` (via `page.tsx:handleMoveCard`). React updater functions passed to `setState` must be pure — React can and does invoke them more than once (React Strict Mode in development deliberately double-invokes state updaters to surface exactly this kind of bug). Every other mutation handler in this same file (`handleRenameColumn`, `handleEditCard`, `handleDeleteCard`) correctly calls its `on*` callback *after* `setBoard(...)`, outside the updater — `handleDragEnd` is the one inconsistent case.

**Action:** compute `nextColumns` with a plain functional update, then call `onMoveCard` afterward, mirroring the other three handlers:
```tsx
setBoard((prev) => ({ ...prev, columns: moveCard(prev.columns, activeId, overId) }));
onMoveCard?.(activeId, overId, moveCard(board.columns, activeId, overId));
```
(or capture `nextColumns` via a ref/variable computed once before calling `setBoard`).

**Status: Fixed.** `nextColumns` is now computed once from `board.columns` before calling `setBoard`, and `onMoveCard` is called after, mirroring the other three handlers.

### 4. AI-supplied action data can crash the chat endpoint with a raw 500
**File:** `backend/app/ai.py`

- `apply_actions` (line 128 onward) does `int(action.columnId)` / `int(action.cardId)` on every action with no error handling. If the model returns a non-numeric id (e.g. it echoes back a frontend-style `"card-3"` instead of `"3"`), this raises an uncaught `ValueError` that FastAPI surfaces as a bare 500, unlike every other OpenRouter failure mode in this file which is deliberately turned into a `502` with a clear `detail` (see `call_openrouter`, `parse_structured_output`).
- `parse_structured_output` (line 25) calls `StructuredChatOutput.model_validate(data)` outside any try/except; a payload that parses as JSON but doesn't match the discriminated-union action schema raises an uncaught pydantic `ValidationError`, same problem.

**Action:** wrap both in try/except and either skip the offending action (log + continue) or raise the same `HTTPException(502, ...)` convention already used elsewhere in this file, so a model hiccup degrades gracefully instead of a 500.

**Status: Fixed.** `parse_structured_output` now catches `pydantic.ValidationError` and raises the same 502. `apply_actions` parses each action's id(s) once per loop iteration inside a `try/except (TypeError, ValueError): continue`, skipping malformed actions instead of crashing (also removed the repeated `int(...)` calls in favor of the parsed locals).

### 5. No CORS support — `npm run dev` can't talk to the backend
**File:** `backend/app/main.py` (no `CORSMiddleware`); `CLAUDE.md`/`frontend/AGENTS.md` list `npm run dev` as a normal dev command.

The app only works cross-origin-free because production serves the built frontend *from* FastAPI. Run `npm run dev` (port 3000) against the FastAPI backend (port 8000) and every `fetch` in `frontend/src/lib/api.ts` will fail: there's no proxy/rewrite (`next.config.ts` uses `output: "export"`, which doesn't support rewrites) and the backend sends no `Access-Control-Allow-Origin` header.

**Action:** either add a scoped `CORSMiddleware` (allow `http://localhost:3000` only) for local dev, or document in `frontend/AGENTS.md` that `npm run dev` is UI-only / requires manually setting `NEXT_PUBLIC_API_BASE` and won't hit a real backend without it.

**Status: Fixed.** Added `CORSMiddleware` in `backend/app/main.py`, scoped to `http://localhost:3000` / `http://127.0.0.1:3000`. Noted in `backend/AGENTS.md`.

### 6. `.dockerignore` doesn't exclude local dev artifacts
**File:** `.dockerignore`

Excludes `node_modules`, `.next`, `test-results`, and pytest caches, but not `backend/.venv`, `backend/data/` (the runtime SQLite path from `backend/app/config.py:get_db_path`), or `backend/tests/`. Confirmed concretely this session: creating a local `backend/.venv` to run tests (~32MB) was not excluded and would be copied into the Docker build context/image by `COPY backend /app/backend` in the `Dockerfile`. A developer's local `pm.db` would be baked into the image the same way if it exists at build time.

**Action:** add to `.dockerignore`:
```
backend/.venv
**/.venv
backend/data
backend/tests
backend/.pytest_cache
```

**Status: Fixed.** Added `backend/.venv`, `**/.venv`, `backend/data`, and `backend/tests` to `.dockerignore` (`backend/.pytest_cache` was already there).

## Low / cleanup

### 7. Duplicate `get_db`
**Files:** `backend/app/database.py:78-83` and `backend/app/dependencies.py:10-15`

Byte-for-byte identical generator function defined twice. Every route imports the one in `dependencies.py` (`backend/app/routes/board.py`, `backend/app/routes/chat.py`); the copy in `database.py` has no callers anywhere in the app or tests.

**Action:** delete `get_db` from `database.py`.

**Status: Fixed.** Removed the dead copy (and the now-unused `Generator` import) from `database.py`.

### 8. Position-clamping logic duplicated five times
**Files:** `backend/app/routes/board.py` (`create_column`, `update_column`, `create_card`, `update_card`) and `backend/app/ai.py` (`create_card`/`move_card` actions)

The same three-line pattern repeats verbatim in five places:
```python
insert_position = position
if insert_position is None or insert_position > len(ids):
    insert_position = len(ids)
if insert_position < 0:
    insert_position = 0
```
**Action:** extract to a single helper, e.g. `clamp_position(position: int | None, upper_bound: int) -> int` in `database.py`, and use it in all five call sites. Purely a DRY cleanup — no behavior change.

**Status: Fixed.** Added `clamp_position` to `database.py` and replaced all six call sites (four in `board.py`, two in `ai.py` — one more than originally counted here) with it. No behavior change; full test suite still passes.

### 9. Column create/delete API is unused and under-tested relative to its access surface
**Files:** `backend/app/routes/board.py` (`create_column`, `delete_column`)

The product requirement is "fixed columns that can be renamed" (`AGENTS.md`), and neither the frontend (`frontend/src/lib/api.ts` has no `createColumn`/`deleteColumn`) nor the AI action schema (`docs/ai-structured-output.json` has no `create_column`/`delete_column` action) ever calls these routes. They're only reachable by a direct API request. This isn't a bug, but it's unexercised surface area that contradicts the stated product design.

**Action:** either remove the two routes (and their models) since nothing in the product uses them, or keep them but note in `backend/AGENTS.md` that they're intentionally-unused future API surface.

**Status: Fixed (documented, not removed).** Both routes are covered by passing tests in `test_board_api.py` (`test_create_and_rename_column`, `test_delete_column_removes_cards`); removing them would mean deleting working, tested code for no functional gain. Added a comment above `create_column`/`delete_column` in `board.py` and a note in `backend/AGENTS.md` explaining they're intentional, currently UI-unexposed API surface.

### 10. Test isolation: raw `os.environ` mutation instead of `monkeypatch`
**File:** `backend/tests/test_board_api.py:10-13` (`_make_client`)

```python
os.environ["PM_DB_PATH"] = str(tmp_path / "test.db")
```
Sets a process-global env var directly with no teardown/restoration. Pytest's `monkeypatch.setenv` fixture would auto-restore the previous value after each test; as written, whichever test in the session runs next inherits this `PM_DB_PATH` pointing at an already-cleaned-up `tmp_path`. Doesn't currently cause a visible failure (the full suite passes), but it's order-dependent test pollution waiting to bite.

**Action:** change `_make_client` to accept `monkeypatch` and use `monkeypatch.setenv("PM_DB_PATH", ...)`.

**Status: Fixed.** `_make_client` now takes `monkeypatch: pytest.MonkeyPatch` and uses `monkeypatch.setenv`; all four call sites updated.

## Already fixed this session (for continuity)

Two bugs were found and fixed earlier in this session, before this full-repo pass — recorded here so this is a complete record of review activity:

- **`frontend/src/components/KanbanCard.tsx`** — dnd-kit's `useSortable({ disabled: isEditing })` attributes (`role="button"`, `aria-disabled`) were spread onto the card unconditionally, so entering edit mode marked the whole card `aria-disabled="true"`, which real browsers cascade to descendants — the edit form was effectively announced as disabled to assistive tech and to Playwright's actionability checks. Fixed by only spreading `attributes`/`listeners` when not editing.
- **`frontend/tests/kanban.spec.ts`** ("edits a card") — the test located the card via `hasText: "Align roadmap themes"`, which stopped matching once editing moved that text into an `<input value>` (not part of `textContent`), hanging the test until timeout. Fixed by re-locating via the card's stable `data-testid` after entering edit mode.

## What's solid

- Backend routes consistently scope every query to `board_id`/`user_id` derived from the (trusted-header) username — no cross-board data leakage once you accept finding #2's premise.
- `resequence_positions` validates its `table` parameter against a whitelist (`VALID_TABLES`) before interpolating it into SQL — the one place a table name is built dynamically, and it's done safely.
- All SQL elsewhere uses parameterized queries; no injectable string-built queries found.
- No `dangerouslySetInnerHTML`, `eval`, or raw `innerHTML` anywhere in the frontend — React's default escaping covers card/chat content, so AI-generated text can't inject markup.
- SQLite connections are opened per-request and always closed in a `finally` (`get_db` in `dependencies.py`) — no connection leaks, no cross-thread reuse.
- `.env` is correctly gitignored and not baked into the image (env vars are injected at `docker run` via `--env-file`); `docker run` never prints or logs the API key.
- Test suite is genuinely meaningful, not just coverage padding: it covers the JSON-repair path in `parse_structured_output`, static-file fallback edge cases, and a real (non-mocked) OpenRouter round trip in `test_integration.py`.

## Suggested priority order (historical)

This was the priority order at review time; all items are now fixed (except #2, deliberately) as noted above.

1. Fix the path traversal (#1) — cheap fix, real vulnerability class.
2. Fix the impure `setState` updater (#3) — cheap fix, prevents duplicate API calls in dev.
3. Harden `ai.py` against malformed model output (#4).
4. Tighten `.dockerignore` (#6) before the next image build.
5. Everything else (#5, #7-#10) is low-risk cleanup — batch whenever convenient.
