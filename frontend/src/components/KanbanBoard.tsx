"use client";

import { useMemo, useRef, useState, type ReactNode } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
  pointerWithin,
  rectIntersection,
  MeasuringStrategy,
  type CollisionDetection,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { KanbanColumn } from "@/components/KanbanColumn";
import { KanbanCardPreview } from "@/components/KanbanCardPreview";
import { createId, moveCard, type BoardData, type Column } from "@/lib/kanban";

type KanbanBoardProps = {
  board: BoardData;
  onBoardChange: React.Dispatch<React.SetStateAction<BoardData>>;
  onLogout?: () => void;
  onRenameColumn?: (columnId: string, title: string) => void;
  onAddCard?: (columnId: string, title: string, details: string) => void;
  onEditCard?: (cardId: string, title: string, details: string) => void;
  onDeleteCard?: (columnId: string, cardId: string) => void;
  onMoveCard?: (activeId: string, overId: string, nextColumns: Column[]) => void;
  sidebar?: ReactNode;
};

export const KanbanBoard = ({
  board,
  onBoardChange,
  onLogout,
  onRenameColumn,
  onAddCard,
  onEditCard,
  onDeleteCard,
  onMoveCard,
  sidebar,
}: KanbanBoardProps) => {
  const setBoard = onBoardChange;
  const [activeCardId, setActiveCardId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    })
  );

  const cardsById = useMemo(() => board.cards, [board.cards]);
  const lastOverId = useRef<string | null>(null);

  const collisionDetection: CollisionDetection = useMemo(
    () => (args) => {
      const filtered = {
        ...args,
        droppableContainers: args.droppableContainers.filter(
          (container) => container.id !== args.active.id
        ),
      };
      const pointerCollisions = pointerWithin(filtered);
      if (pointerCollisions.length > 0) {
        return pointerCollisions;
      }
      const intersections = rectIntersection(filtered);
      if (intersections.length > 0) {
        return intersections;
      }
      return closestCorners(filtered);
    },
    []
  );

  const handleDragStart = (event: DragStartEvent) => {
    const activeId = event.active.data.current?.cardId as string | undefined;
    if (!activeId) {
      return;
    }
    setActiveCardId(activeId);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveCardId(null);

    const activeId = active.data.current?.cardId as string | undefined;
    const activeColumnId = active.data.current?.columnId as string | undefined;
    const overIdFromData = over?.data.current?.cardId as string | undefined;
    const overColumnFromData = over?.data.current?.columnId as string | undefined;
    const isCrossColumn =
      activeColumnId && overColumnFromData && activeColumnId !== overColumnFromData;
    const resolvedOverId =
      (overIdFromData && overIdFromData !== activeId && !isCrossColumn
        ? overIdFromData
        : undefined) ??
      overColumnFromData ??
      lastOverId.current;
    if (!activeId || !resolvedOverId || activeId === resolvedOverId) {
      lastOverId.current = null;
      return;
    }

    const overId = resolvedOverId;
    const nextColumns = moveCard(board.columns, activeId, overId);

    setBoard((prev) => ({ ...prev, columns: nextColumns }));
    onMoveCard?.(activeId, overId, nextColumns);

    lastOverId.current = null;
  };

  const handleDragOver = (event: { active: DragEndEvent["active"]; over: DragEndEvent["over"] }) => {
    if (event.over) {
      const activeColumnId = event.active.data.current?.columnId as string | undefined;
      const overCardId = event.over.data.current?.cardId as string | undefined;
      const overColumnId = event.over.data.current?.columnId as string | undefined;
      if (activeColumnId && overColumnId && activeColumnId !== overColumnId) {
        lastOverId.current = overColumnId;
        return;
      }
      lastOverId.current = overCardId ?? overColumnId ?? null;
    }
  };

  const handleRenameColumn = (columnId: string, title: string) => {
    setBoard((prev) => ({
      ...prev,
      columns: prev.columns.map((column) =>
        column.id === columnId ? { ...column, title } : column
      ),
    }));
    onRenameColumn?.(columnId, title);
  };

  const handleAddCard = (columnId: string, title: string, details: string) => {
    if (onAddCard) {
      onAddCard(columnId, title, details);
      return;
    }
    const id = createId("card");
    setBoard((prev) => ({
      ...prev,
      cards: {
        ...prev.cards,
        [id]: { id, title, details: details || "No details yet." },
      },
      columns: prev.columns.map((column) =>
        column.id === columnId
          ? { ...column, cardIds: [...column.cardIds, id] }
          : column
      ),
    }));
  };

  const handleEditCard = (cardId: string, title: string, details: string) => {
    setBoard((prev) => ({
      ...prev,
      cards: {
        ...prev.cards,
        [cardId]: { ...prev.cards[cardId], title, details },
      },
    }));
    onEditCard?.(cardId, title, details);
  };

  const handleDeleteCard = (columnId: string, cardId: string) => {
    setBoard((prev) => {
      return {
        ...prev,
        cards: Object.fromEntries(
          Object.entries(prev.cards).filter(([id]) => id !== cardId)
        ),
        columns: prev.columns.map((column) =>
          column.id === columnId
            ? {
              ...column,
              cardIds: column.cardIds.filter((id) => id !== cardId),
            }
            : column
        ),
      };
    });
    onDeleteCard?.(columnId, cardId);
  };

  const activeCard = activeCardId ? cardsById[activeCardId] : null;

  return (
    <div className="relative overflow-hidden">
      <div className="pointer-events-none absolute left-0 top-0 h-[420px] w-[420px] -translate-x-1/3 -translate-y-1/3 rounded-full bg-[radial-gradient(circle,_rgba(32,157,215,0.25)_0%,_rgba(32,157,215,0.05)_55%,_transparent_70%)]" />
      <div className="pointer-events-none absolute bottom-0 right-0 h-[520px] w-[520px] translate-x-1/4 translate-y-1/4 rounded-full bg-[radial-gradient(circle,_rgba(117,57,145,0.18)_0%,_rgba(117,57,145,0.05)_55%,_transparent_75%)]" />

      <main className="relative mx-auto flex min-h-screen max-w-[1500px] flex-col gap-10 px-6 pb-16 pt-12">
        <header className="flex flex-col gap-6 rounded-[32px] border border-[var(--stroke)] bg-white/80 p-8 shadow-[var(--shadow)] backdrop-blur">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.35em] text-[var(--gray-text)]">
                Single Board Kanban
              </p>
              <h1 className="mt-3 font-display text-4xl font-semibold text-[var(--navy-dark)]">
                Kanban Studio
              </h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-[var(--gray-text)]">
                Keep momentum visible. Rename columns, edit and drag cards
                between stages, and capture quick notes without getting buried
                in settings.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3">
              {onLogout ? (
                <button
                  type="button"
                  onClick={onLogout}
                  className="rounded-full border border-[var(--stroke)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--navy-dark)] transition hover:border-[var(--primary-blue)]"
                >
                  Log out
                </button>
              ) : null}
              <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--surface)] px-5 py-4">
                <p className="text-xs font-semibold uppercase tracking-[0.25em] text-[var(--gray-text)]">
                  Focus
                </p>
                <p className="mt-2 text-lg font-semibold text-[var(--primary-blue)]">
                  One board. Five columns. Zero clutter.
                </p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            {board.columns.map((column) => (
              <div
                key={column.id}
                className="flex items-center gap-2 rounded-full border border-[var(--stroke)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--navy-dark)]"
              >
                <span className="h-2 w-2 rounded-full bg-[var(--accent-yellow)]" />
                {column.title}
              </div>
            ))}
          </div>
        </header>

        <div className={sidebar ? "grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]" : ""}>
          <DndContext
            sensors={sensors}
            measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}
            collisionDetection={collisionDetection}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDragEnd={handleDragEnd}
          >
            <section className="grid gap-6 lg:grid-cols-5">
              {board.columns.map((column) => (
                <KanbanColumn
                  key={column.id}
                  column={column}
                  cards={column.cardIds.map((cardId) => board.cards[cardId])}
                  onRename={handleRenameColumn}
                  onAddCard={handleAddCard}
                  onEditCard={handleEditCard}
                  onDeleteCard={handleDeleteCard}
                />
              ))}
            </section>
            <DragOverlay>
              {activeCard ? (
                <div className="w-[260px]">
                  <KanbanCardPreview card={activeCard} />
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>
          {sidebar ? (
            <div className="lg:sticky lg:top-10 lg:self-start">
              {sidebar}
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
};
