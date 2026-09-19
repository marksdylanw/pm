# Frontend overview

## Stack
- Next.js 16 App Router (static export)
- React 19
- TypeScript
- Tailwind CSS v4 (via @tailwindcss/postcss)
- Drag-and-drop via @dnd-kit
- Unit testing with Vitest and Testing Library
- E2E testing with Playwright against the backend-served app

## Entry points
- App shell: src/app/layout.tsx
- Home route: src/app/page.tsx
  - Login screen when unauthenticated (demo credentials: user / password)
  - Loads the persisted board from `/api/board` after sign-in
  - Owns chat history and wires Kanban mutations to the backend API
- Global styles: src/app/globals.css

## UI components
- KanbanBoard: src/components/KanbanBoard.tsx
  - Receives board state from page.tsx
  - Handles drag-and-drop, column rename, add/edit/delete cards
  - Uses DndContext + DragOverlay
  - Optional sidebar slot for AI chat
- KanbanColumn: src/components/KanbanColumn.tsx
  - Droppable column surface
  - Renders column header, cards list, and NewCardForm
- KanbanCard: src/components/KanbanCard.tsx
  - Sortable card
  - Displays title/details with Edit and Remove
  - Inline form to save title and details
- KanbanCardPreview: src/components/KanbanCardPreview.tsx
  - Visual preview used in drag overlay
- NewCardForm: src/components/NewCardForm.tsx
  - Inline form to add cards (title required, details optional)
- ChatSidebar: src/components/ChatSidebar.tsx
  - Conversation history and send box
  - AI replies can include board updates that page.tsx applies immediately

## Data model and API
- Types and drag helpers: src/lib/kanban.ts
  - Types: Card, Column, BoardData
  - initialData: demo board used by unit tests
  - moveCard, findCardLocation, createId
  - toColumnId / toCardId prefix backend numeric ids (`col-`, `card-`); fromColumnId / fromCardId strip them before API calls
- API client: src/lib/api.ts
  - fetchBoard, createCard, updateCard, deleteCard, updateColumn, sendChat
  - toBoardData maps API payloads onto the prefixed frontend ids
  - Sends `X-User` for the signed-in username

## Tests
- Unit tests
  - src/app/page.test.tsx
  - src/components/KanbanBoard.test.tsx
  - src/components/ChatSidebar.test.tsx
  - src/components/KanbanCardPreview.test.tsx
  - src/lib/kanban.test.ts
- Test setup: src/test/setup.ts
- E2E tests: tests/kanban.spec.ts (Playwright hits the Docker app at port 8000)

## Build and scripts
- Scripts: package.json
  - dev, build, start, lint
  - test:unit, test:e2e, test:all
- next.config.ts uses static export so FastAPI can serve `out/` from the container
