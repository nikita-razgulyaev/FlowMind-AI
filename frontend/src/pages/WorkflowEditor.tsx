import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
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
    type Node,
    type Edge,
    type Connection,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Save, Play, Sparkles, Terminal } from "lucide-react";
import { api } from "../api/client";
import type { WorkflowNode, WorkflowEdge } from "../types/workflow";
import CanvasNode, { NODE_META, BRANCH_HANDLE_PREFIX, branchColor } from "../components/canvas/CanvasNode";
import NodeConfigPanel from "../components/canvas/NodeConfigPanel";
import EditorSidebar from "../components/canvas/EditorSidebar";
import ChatLogPanel from "../components/canvas/ChatLogPanel";
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
};

const PALETTE: { type: string }[] = [
    { type: "manual" },
    { type: "telegram_trigger" },
    { type: "webhook" },
    { type: "schedule" },
    { type: "http" },
    { type: "telegram_send" },
    { type: "google_sheets_append" },
    { type: "google_calendar_create_event" },
    { type: "llm" },
    { type: "agent" },
    { type: "condition" },
    { type: "switch" },
    { type: "set" },
    { type: "print" },
];

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

/** После загрузки нод подгоняет зум так, чтобы весь граф был на экране. */
function FitViewOnLoad({ nodeCount }: { nodeCount: number }) {
    const { fitView } = useReactFlow();
    useEffect(() => {
        if (nodeCount <= 0) return;
        const t = requestAnimationFrame(() => {
            fitView({ padding: 0.2, maxZoom: 1, duration: 400 });
        });
        return () => cancelAnimationFrame(t);
    }, [nodeCount, fitView]);
    return null;
}

export default function WorkflowEditor() {
    const { id } = useParams();
    const navigate = useNavigate();
    const isEditing = !!id;

    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [runStatus, setRunStatus] = useState<string | null>(null);
    const [showLog, setShowLog] = useState(false);
    const [showAiChat, setShowAiChat] = useState(false);
    const [isActive, setIsActive] = useState(true);
    const [lastExecution, setLastExecution] = useState<{
        triggerInput?: string;
        logs: any[];
    } | null>(null);
    const idCounter = useRef(0);

    useEffect(() => {
        if (isEditing) loadWorkflow();
    }, [id]);

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
            const { data: execData } = await api.getExecution(
                data.execution_id,
            );
            if (execData) {
                setLastExecution({
                    triggerInput: execData.trigger_data?.input || "",
                    logs: execData.logs || [],
                });
                setShowAiChat(false);
                setShowLog(true);
            }
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
                <div className="flex items-center justify-between px-6 py-3 border-b border-gray-200 bg-white">
                    <div className="flex items-center gap-3">
                        <input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="Название workflow"
                            className="text-lg font-bold text-gray-900 border-none outline-none focus:ring-0 bg-transparent"
                        />
                        <input
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="Описание..."
                            className="text-sm text-gray-400 border-none outline-none focus:ring-0 bg-transparent w-64"
                        />
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
                            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border ${
                                showAiChat
                                    ? "border-indigo-300 bg-indigo-50 text-indigo-700"
                                    : "border-gray-200 text-gray-600 hover:bg-gray-50"
                            }`}
                        >
                            <Sparkles className="w-4 h-4" /> AI-чат
                        </button>
                        <button
                            onClick={() => setShowLog((v) => !v)}
                            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border ${
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
                            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium"
                        >
                            <Play className="w-4 h-4" /> Run
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={isLoading}
                            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                        >
                            <Save className="w-4 h-4" />{" "}
                            {isLoading ? "Сохранение..." : "Save"}
                        </button>
                    </div>
                </div>

                <div className="flex items-center gap-2 px-6 py-2 border-b border-gray-100 bg-white overflow-x-auto">
                    {PALETTE.map(({ type }) => {
                        const meta = NODE_META[type];
                        const Icon = meta.icon;
                        return (
                            <button
                                key={type}
                                onClick={() => addNode(type)}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap ${meta.badge} hover:opacity-80`}
                            >
                                <Icon className="w-3.5 h-3.5" /> + {meta.label}
                            </button>
                        );
                    })}
                </div>

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
                                fitView
                                fitViewOptions={{
                                    maxZoom: 1,
                                    minZoom: 0.15,
                                    padding: 0.25,
                                }}
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
                                    className="!bg-white"
                                />
                            </ReactFlow>
                        </ReactFlowProvider>

                        {nodes.length === 0 && (
                            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                <p className="text-gray-400 text-sm">
                                    Добавь ноду из панели выше, чтобы начать
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
                        triggerInput={lastExecution?.triggerInput}
                        logs={lastExecution?.logs || []}
                        onClose={() => setShowLog(false)}
                    />
                )}
            </div>
        </div>
    );
}
