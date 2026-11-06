import { useCallback, useEffect, useRef } from "react";
import type { Edge, Node } from "@xyflow/react";

interface Snapshot {
    nodes: Node[];
    edges: Edge[];
}

const HISTORY_LIMIT = 50;

/**
 * Отмена/повтор правок графа (Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y).
 * Вызывай `snapshot()` перед изменением графа; поля ввода сохраняют своё родное отменение текста.
 */
export function useGraphHistory(
    nodes: Node[],
    edges: Edge[],
    apply: (nodes: Node[], edges: Edge[]) => void,
) {
    const past = useRef<Snapshot[]>([]);
    const future = useRef<Snapshot[]>([]);
    const latest = useRef<Snapshot>({ nodes, edges });
    latest.current = { nodes, edges };
    const applyRef = useRef(apply);
    applyRef.current = apply;

    const snapshot = useCallback(() => {
        const top = past.current[past.current.length - 1];
        // несколько изменений за один тик (удаление ноды + её связей) — одна точка отката
        if (top && top.nodes === latest.current.nodes && top.edges === latest.current.edges) return;
        past.current.push(latest.current);
        if (past.current.length > HISTORY_LIMIT) past.current.shift();
        future.current = [];
    }, []);

    const undo = useCallback(() => {
        const previous = past.current.pop();
        if (!previous) return;
        future.current.push(latest.current);
        applyRef.current(previous.nodes, previous.edges);
    }, []);

    const redo = useCallback(() => {
        const next = future.current.pop();
        if (!next) return;
        past.current.push(latest.current);
        applyRef.current(next.nodes, next.edges);
    }, []);

    const reset = useCallback(() => {
        past.current = [];
        future.current = [];
    }, []);

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (!(e.ctrlKey || e.metaKey)) return;
            const target = e.target as HTMLElement | null;
            if (target?.closest?.("input, textarea, select, [contenteditable='true']")) return;
            // e.code не зависит от раскладки (на русской Ctrl+Z даёт key = «я»)
            if (e.code === "KeyZ" && !e.shiftKey) {
                e.preventDefault();
                undo();
            } else if ((e.code === "KeyZ" && e.shiftKey) || e.code === "KeyY") {
                e.preventDefault();
                redo();
            }
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [undo, redo]);

    return { snapshot, reset };
}
