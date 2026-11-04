import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
    ReactFlow,
    ReactFlowProvider,
    Background,
    Controls,
    MiniMap,
    addEdge,
    useNodesState,
    useEdgesState,
    useReactFlow,
    useNodesInitialized,
    type Node,
    type Edge,
    type Connection,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Save, Play, Sparkles, Terminal } from "lucide-react";
import { api } from "../api/client";
import type { WorkflowNode, WorkflowEdge } from "../types/workflow";
import CanvasNode, { BRANCH_HANDLE_PREFIX, MINIMAP_COLORS, branchColor } from "../components/canvas/CanvasNode";
import NodePalette from "../components/canvas/NodePalette";
import MiniMapNode from "../components/canvas/MiniMapNode";
import NodeConfigPanel from "../components/canvas/NodeConfigPanel";
import EditorSidebar from "../components/canvas/EditorSidebar";
import ChatLogPanel from "../components/canvas/ChatLogPanel";
import type { ExecutionRecord } from "../utils/executionLog";
import AiChatPanel from "../components/canvas/AiChatPanel";
import { getSettings } from "../utils/settings";

const nodeTypes = {
    manual: CanvasNode,
    telegram_trigger: CanvasNode,
    schedule: CanvasNode,
    llm: CanvasNode,
    http: CanvasNode,
    condition: CanvasNode,
    print: CanvasNode,
    agent: CanvasNode,
    telegram_send: CanvasNode,
    google_sheets_append: CanvasNode,
    google_calendar_create_event: CanvasNode,
    webhook: CanvasNode,
    switch: CanvasNode,
    set: CanvasNode,
    text_input: CanvasNode,
};


function defaultConfig(type: string): Record<string, any> {
    const settings = getSettings();
    switch (type) {
        case "llm":
            return {
                model:
                    settings.defaultMode === "local"
                        ? settings.defaultLocalModel
                        : settings.defaultCloudModel,
                prompt: "",
                temperature: settings.defaultTemperature,
                mode: settings.defaultMode,
            };
        case "telegram_trigger":
            return {
                connection_id: undefined,
                allowed_chat_ids: "",
                only_commands: false,
                test_input: "",
                test_chat_id: "",
            };
        case "http":
            return { method: "GET", url: "" };
        case "telegram_send":
            return { connection_id: undefined, chat_id: "", message: "" };
        case "google_sheets_append":
            return {
                connection_id: undefined,
                spreadsheet_id: "",
                range: "A1",
                values: "",
            };
        case "google_calendar_create_event":
            return {
                connection_id: undefined,
                calendar_id: "primary",
                summary: "",
                description: "",
                start_datetime: "",
                end_datetime: "",
            };
        case "print":
            return { value: "" };
        case "agent":
            return {
                system_prompt: "Ты — полезный ассистент.",
                model:
                    settings.defaultMode === "local"
                        ? settings.defaultLocalModel
                        : settings.defaultCloudModel,
                mode: settings.defaultMode,
                max_iterations: 5,
                temperature: settings.defaultTemperature,
                prompt: "{input}",
            };
        case "condition":
            return { expression: "" };
        case "text_input":
            return { text: "", file_name: "" };
        case "switch":
            return { value: "{input}", cases: "" };
        case "set":
            return { values: "" };
        case "schedule":
            return { interval_minutes: 60, test_input: "" };
        case "webhook":
            return { test_input: "" };
        case "manual":
            return { test_input: "" };
        default:
            return {};
    }
}

function toFlowNode(n: WorkflowNode, index: number): Node {
    return {
        id: n.id,
        type: n.type,
        // Горизонтальная цепочка — ноды не переносятся на следующую строку
        position: n.position || {
            x: 80 + index * 320,
            y: 120,
        },
        data: { config: n.config },
    };
}

/** Стиль связи по типу: tool — пунктир, ветка Condition/Switch — цвет и подпись метки. */
function edgeStyle(kind: "tool" | "branch" | "next", label?: string) {
    if (kind === "tool") return { stroke: "#6366f1", strokeDasharray: "4 3" };
    if (kind === "branch") return { stroke: branchColor(label || "") };
    return { stroke: "#3b82f6" };
}

function toFlowEdge(e: WorkflowEdge): Edge {
    const isTool = e.type === "tool";
    const isBranch = !isTool && !!e.condition;
    return {
        id: e.id,
        source: e.from_node,
        target: e.to_node,
        // Явные id handle'ов — без targetHandle React Flow не рисует линию к ноде с id="in"
        sourceHandle: isTool
            ? "out-tool"
            : isBranch
              ? `${BRANCH_HANDLE_PREFIX}${e.condition}`
              : "out-next",
        targetHandle: "in",
        animated: isTool,
        style: edgeStyle(isTool ? "tool" : isBranch ? "branch" : "next", e.condition),
        label: isTool ? "tool" : e.condition,
    };
}

/** Подгоняет граф по центру, когда ноды измерены (иначе fitView считает по нодам без размеров и сдвигает граф). */
function FitViewOnLoad({ nodeCount }: { nodeCount: number }) {
    const { fitView } = useReactFlow();
    const initialized = useNodesInitialized();
    useEffect(() => {
        if (!initialized || nodeCount <= 0) return;
        const t = setTimeout(() => fitView({ padding: 0.2, maxZoom: 1, duration: 300 }), 60);
        return () => clearTimeout(t);
    }, [initialized, nodeCount, fitView]);
    return null;
}

export default function WorkflowEditor() {
    const { id } = useParams();
    const [searchParams] = useSearchParams();
    const logParam = Number(searchParams.get("log")) || null;   // переход из истории выполнений
    const navigate = useNavigate();
    const isEditing = !!id;

    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [descriptionDraft, setDescriptionDraft] = useState<string | null>(null);   // не null — модалка открыта
    const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [runStatus, setRunStatus] = useState<string | null>(null);
    const [showLog, setShowLog] = useState(logParam !== null);
    const [showAiChat, setShowAiChat] = useState(false);
    const [isActive, setIsActive] = useState(true);
    const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
    const [focusExecutionId, setFocusExecutionId] = useState<number | null>(logParam);
    const idCounter = useRef(0);

    useEffect(() => {
        if (isEditing) {
            loadWorkflow();
            loadExecutions();
        }
    }, [id]);

    useEffect(() => {
        if (logParam) {
            setFocusExecutionId(logParam);
            setShowLog(true);
            setSelectedId(null);
        }
    }, [logParam]);

    const loadExecutions = async () => {
        const { data } = await api.getExecutions(Number(id));
        if (data) setExecutions(data);
    };

    const clearLogs = async () => {
        if (!window.confirm(`Удалить запуски этого воркфлоу (${executions.length}) из истории выполнений?`)) return;
        const { error } = await api.bulkDeleteExecutions(executions.map((e) => e.id));
        if (error) {
            alert(`Ошибка: ${error}`);
            return;
        }
        setExecutions([]);
        setFocusExecutionId(null);
        setRunStatus(null);
    };

    const loadWorkflow = async () => {
        const { data } = await api.getWorkflow(Number(id));
        if (data) {
            setName(data.name);
            setDescription(data.description);
            setIsActive(data.is_active);
            setNodes(data.nodes.map(toFlowNode));
            // edges после nodes: handles должны успеть смонтироваться
            const mapped = (data.edges || []).map(toFlowEdge);
            requestAnimationFrame(() => setEdges(mapped));
        }
    };

    const genId = (type: string) => {
        idCounter.current += 1;
        return `${type}_${Date.now()}_${idCounter.current}`;
    };

    const addNode = (type: string) => {
        const newId = genId(type);
        const count = nodes.length;
        const newNode: Node = {
            id: newId,
            type,
            position: {
                x: 80 + count * 320,
                y: 120,
            },
            data: { config: defaultConfig(type) },
        };
        setNodes((nds) => [...nds, newNode]);
        setSelectedId(newId);
    };

    const onConnect = useCallback(
        (connection: Connection) => {
            const handle = connection.sourceHandle || "out-next";
            const isTool = handle === "out-tool";
            const branch = handle.startsWith(BRANCH_HANDLE_PREFIX)
                ? handle.slice(BRANCH_HANDLE_PREFIX.length)
                : undefined;
            setEdges((eds) =>
                addEdge(
                    {
                        ...connection,
                        sourceHandle: handle,
                        targetHandle: connection.targetHandle || "in",
                        animated: isTool,
                        style: edgeStyle(isTool ? "tool" : branch ? "branch" : "next", branch),
                        label: isTool ? "tool" : branch,
                    },
                    eds,
                ),
            );
        },
        [setEdges],
    );

    const updateSelectedConfig = (config: Record<string, any>) => {
        if (!selectedId) return;
        setNodes((nds) =>
            nds.map((n) =>
                n.id === selectedId ? { ...n, data: { ...n.data, config } } : n,
            ),
        );
    };

    const deleteSelected = () => {
        if (!selectedId) return;
        setNodes((nds) => nds.filter((n) => n.id !== selectedId));
        setEdges((eds) =>
            eds.filter(
                (e) => e.source !== selectedId && e.target !== selectedId,
            ),
        );
        setSelectedId(null);
    };

    const selectedNode = nodes.find((n) => n.id === selectedId);

    const buildPayload = () => ({
        name,
        description,
        nodes: nodes.map(
            (n): WorkflowNode => ({
                id: n.id,
                type: n.type as WorkflowNode["type"],
                config: (n.data?.config as Record<string, any>) || {},
                position: n.position,
            }),
        ),
        edges: edges.map(
            (e): WorkflowEdge => ({
                id: e.id,
                from_node: e.source,
                to_node: e.target,
                type: e.sourceHandle === "out-tool" ? "tool" : "next",
                condition: e.sourceHandle?.startsWith(BRANCH_HANDLE_PREFIX)
                    ? e.sourceHandle.slice(BRANCH_HANDLE_PREFIX.length)
                    : undefined,
            }),
        ),
        is_active: isActive,
    });

    const applyAiGraph = (graph: { nodes: any[]; edges: any[] }) => {
        setNodes(graph.nodes.map(toFlowNode));
        const mapped = (graph.edges || []).map(toFlowEdge);
        requestAnimationFrame(() => setEdges(mapped));
        setSelectedId(null);
    };

    const hasTelegramTrigger = nodes.some((n) => n.type === "telegram_trigger");

    const handleSave = async () => {
        setIsLoading(true);
        const payload = buildPayload();
        const { data, error } = isEditing
            ? await api.updateWorkflow(Number(id), payload)
            : await api.createWorkflow(payload);

        if (data) {
            if (!isEditing) navigate(`/workflow/${data.id}`);
        }
        if (error) alert(`Error: ${error}`);
        setIsLoading(false);
    };

    /** Run без модалки: тестовые данные берутся из настроек триггера (поле «Тестовые данные»). */
    const runWorkflow = async () => {
        setRunStatus("Выполняется...");
        const { data, error } = await api.executeWorkflow(Number(id), {
            input: "",
        });
        if (data) {
            setRunStatus(
                `Готово — execution #${data.execution_id} (${data.status})`,
            );
            await loadExecutions();
            setFocusExecutionId(data.execution_id);
            setShowAiChat(false);
            setShowLog(true);
        }
        if (error) setRunStatus(`Ошибка: ${error}`);
    };

    const handleExecute = async () => {
        if (!isEditing) {
            alert("Сохрани workflow перед запуском");
            return;
        }
        await runWorkflow();
    };

    return (
        <div className="flex h-screen">
            <EditorSidebar />
            <div className="flex-1 flex flex-col min-w-0">
                <div className="flex items-center justify-between px-6 py-2 border-b border-gray-200 bg-white">
                    <div className="flex items-center gap-3">
                        <input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="Название workflow"
                            className="text-lg font-bold text-gray-900 border-none outline-none focus:ring-0 bg-transparent"
                        />
                        <button
                            onClick={() => setDescriptionDraft(description)}
                            title="Изменить описание"
                            className="max-w-xs truncate text-sm text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded px-2 py-1"
                        >
                            {description || "Добавить описание..."}
                        </button>
                    </div>
                    <div className="flex items-center gap-3">
                        {runStatus && (
                            <span className="text-xs text-gray-500 bg-gray-100 px-2.5 py-1 rounded-full">
                                {runStatus}
                            </span>
                        )}
                        {hasTelegramTrigger && (
                            <label
                                className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer select-none"
                                title="Пока воркфлоу активен, Telegram-триггер принимает сообщения"
                            >
                                <input
                                    type="checkbox"
                                    checked={isActive}
                                    onChange={(e) =>
                                        setIsActive(e.target.checked)
                                    }
                                />
                                Активен
                            </label>
                        )}
                        <button
                            onClick={() => {
                                setShowAiChat((v) => !v);
                            }}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium border ${
                                showAiChat
                                    ? "border-indigo-300 bg-indigo-50 text-indigo-700"
                                    : "border-gray-200 text-gray-600 hover:bg-gray-50"
                            }`}
                        >
                            <Sparkles className="w-4 h-4" /> AI-чат
                        </button>
                        <button
                            onClick={() => setShowLog((v) => !v)}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium border ${
                                showLog
                                    ? "border-gray-300 bg-gray-100 text-gray-700"
                                    : "border-gray-200 text-gray-600 hover:bg-gray-50"
                            }`}
                        >
                            <Terminal className="w-4 h-4" /> Лог
                        </button>
                        <button
                            onClick={handleExecute}
                            disabled={!isEditing}
                            className="flex items-center gap-2 px-4 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium"
                        >
                            <Play className="w-4 h-4" /> Run
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={isLoading}
                            className="flex items-center gap-2 px-4 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                        >
                            <Save className="w-4 h-4" />{" "}
                            {isLoading ? "Сохранение..." : "Save"}
                        </button>
                    </div>
                </div>

                <NodePalette onAdd={addNode} />

                <div className="flex-1 flex min-h-0">
                    <div className="flex-1 relative">
                        <ReactFlowProvider>
                            <ReactFlow
                                nodes={nodes}
                                edges={edges}
                                onNodesChange={onNodesChange}
                                onEdgesChange={onEdgesChange}
                                onConnect={onConnect}
                                isValidConnection={(c) => c.source !== c.target}
                                nodeTypes={nodeTypes}
                                onNodeClick={(_, n) => {
                                    setSelectedId(n.id);
                                    setShowAiChat(false);
                                }}
                                onPaneClick={() => setSelectedId(null)}
                                deleteKeyCode={["Backspace", "Delete"]}
                                minZoom={0.1}
                                maxZoom={1.5}
                                proOptions={{ hideAttribution: true }}
                            >
                                <FitViewOnLoad nodeCount={nodes.length} />
                                <Background gap={20} />
                                <Controls />
                                <MiniMap
                                    pannable
                                    zoomable
                                    nodeComponent={MiniMapNode}
                                    nodeColor={(n) => MINIMAP_COLORS[n.type || ""] || "#9ca3af"}
                                    maskColor="rgba(99, 102, 241, 0.08)"
                                    maskStrokeColor="#6366f1"
                                    maskStrokeWidth={1.5}
                                    style={{ width: 200, height: 130 }}
                                    className="!bg-white/90 !rounded-xl !border !border-gray-200 !shadow-lg overflow-hidden"
                                />
                            </ReactFlow>
                        </ReactFlowProvider>

                        {nodes.length === 0 && (
                            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                <p className="text-gray-400 text-sm">
                                    Добавь ноду из панели инструментов, чтобы начать
                                </p>
                            </div>
                        )}
                    </div>

                    {showAiChat ? (
                        <AiChatPanel
                            getGraph={() => {
                                const p = buildPayload();
                                return { nodes: p.nodes, edges: p.edges };
                            }}
                            onApply={applyAiGraph}
                        />
                    ) : (
                        selectedNode && (
                            <NodeConfigPanel
                                node={{
                                    id: selectedNode.id,
                                    type: selectedNode.type as WorkflowNode["type"],
                                    config:
                                        (selectedNode.data?.config as Record<
                                            string,
                                            any
                                        >) || {},
                                }}
                                workflowId={isEditing ? Number(id) : undefined}
                                onChange={updateSelectedConfig}
                                onDelete={deleteSelected}
                                onClose={() => setSelectedId(null)}
                            />
                        )
                    )}
                </div>

                {showLog && (
                    <ChatLogPanel
                        executions={executions}
                        focusId={focusExecutionId}
                        onClear={clearLogs}
                        onClose={() => setShowLog(false)}
                    />
                )}
            </div>

            {descriptionDraft !== null && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
                    onMouseDown={(e) => e.target === e.currentTarget && setDescriptionDraft(null)}
                >
                    <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-2xl">
                        <h3 className="text-base font-semibold text-gray-900">Описание воркфлоу</h3>
                        <textarea
                            autoFocus
                            value={descriptionDraft}
                            onChange={(e) => setDescriptionDraft(e.target.value)}
                            onKeyDown={(e) => e.key === "Escape" && setDescriptionDraft(null)}
                            maxLength={1000}
                            rows={6}
                            placeholder="Что делает этот воркфлоу..."
                            className="mt-3 w-full rounded-lg border border-gray-200 p-3 text-sm outline-none focus:border-blue-400"
                        />
                        <div className="mt-1 text-right text-xs text-gray-400">{descriptionDraft.length}/1000</div>
                        <div className="mt-3 flex justify-end gap-2">
                            <button
                                onClick={() => setDescriptionDraft(null)}
                                className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
                            >
                                Отмена
                            </button>
                            <button
                                onClick={() => {
                                    setDescription(descriptionDraft);
                                    setDescriptionDraft(null);
                                }}
                                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
                            >
                                Готово
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
