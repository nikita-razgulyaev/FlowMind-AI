// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import type { Edge, Node } from "@xyflow/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { useGraphHistory } from "./useGraphHistory";

const node = (id: string): Node => ({ id, position: { x: 0, y: 0 }, data: {} });

function setup() {
    return renderHook(() => {
        const [nodes, setNodes] = useState<Node[]>([node("a"), node("b")]);
        const [edges, setEdges] = useState<Edge[]>([]);
        const history = useGraphHistory(nodes, edges, (n, e) => {
            setNodes(n);
            setEdges(e);
        });
        return { nodes, setNodes, history };
    });
}

const press = (code: string, shiftKey = false) =>
    act(() => {
        window.dispatchEvent(new KeyboardEvent("keydown", { code, ctrlKey: true, shiftKey }));
    });

describe("useGraphHistory", () => {
    it("Ctrl+Z возвращает удалённую ноду, Ctrl+Shift+Z — удаляет снова (независимо от раскладки)", () => {
        const { result } = setup();
        act(() => {
            result.current.history.snapshot();
            result.current.setNodes((n) => n.filter((x) => x.id !== "a"));
        });
        expect(result.current.nodes.map((n) => n.id)).toEqual(["b"]);

        press("KeyZ");
        expect(result.current.nodes.map((n) => n.id)).toEqual(["a", "b"]);
        press("KeyZ", true);
        expect(result.current.nodes.map((n) => n.id)).toEqual(["b"]);
    });

    it("два snapshot за один тик дают одну точку отката", () => {
        const { result } = setup();
        act(() => {
            result.current.history.snapshot();
            result.current.history.snapshot();
            result.current.setNodes([]);
        });
        press("KeyZ");
        expect(result.current.nodes).toHaveLength(2);
        press("KeyZ");                       // дальше откатывать нечего
        expect(result.current.nodes).toHaveLength(2);
    });
});
