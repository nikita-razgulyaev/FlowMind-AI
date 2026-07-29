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
    type Node,
    type Edge,
    type Connection,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Save, Play, Sparkles, Terminal } from "lucide-react";
import { api } from "../api/client";
import type { WorkflowNode, WorkflowEdge } from "../types/workflow";
import CanvasNode, { NODE_META } from "../components/canvas/CanvasNode";
import NodeConfigPanel from "../components/canvas/NodeConfigPanel";
import EditorSidebar from "../components/canvas/EditorSidebar";
import ChatLogPanel from "../components/canvas/ChatLogPanel";
import AiChatPanel from "../components/canvas/AiChatPanel";
import { getSettings } from "../utils/settings";

const nodeTypes = {
    manual: CanvasNode,
    schedule: CanvasNode,
    llm: CanvasNode,
    http: CanvasNode,
    condition: CanvasNode,
    print: CanvasNode,
    agent: CanvasNode,
    telegram_send: CanvasNode,
};

const PALETTE: { type: string }[] = [
    { type: "manual" },
    { type: "http" },
    { type: "telegram_send" },
    { type: "llm" },
    { type: "agent" },
    { type: "condition" },
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
        case "http":
            return { method: "GET", url: "" };
        case "telegram_send":
            return { connection_id: undefined, chat_id: "", message: "" };
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
        default:
            return {};
    }
}

function toFlowNode(n: WorkflowNode, index: number): Node {
    return {
        id: n.id,
        type: n.type,
        position: n.position || {
            x: 80 + (index % 3) * 300,
            y: 80 + Math.floor(index / 3) * 180,
        },
        data: { config: n.config },
    };
}

function toFlowEdge(e: WorkflowEdge): Edge {
    return {
        id: e.id,
        source: e.from_node,
        target: e.to_node,
        sourceHandle: e.type === "tool" ? "out-tool" : "out-next",
        animated: e.type === "tool",
        style:
            e.type === "tool"
                ? { stroke: "#6366f1", strokeDasharray: "4 3" }
                : { stroke: "#3b82f6" },
        label: e.type === "tool" ? "tool" : undefined,
    };
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
    const [showRunDialog, setShowRunDialog] = useState(false);
    const [runInput, setRunInput] = useState("");
    const [runStatus, setRunStatus] = useState<string | null>(null);
    const [showLog, setShowLog] = useState(false);
    const [showAiChat, setShowAiChat] = useState(false);
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
            setNodes(data.nodes.map(toFlowNode));
            setEdges(data.edges.map(toFlowEdge));
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
                x: 80 + (count % 3) * 300,
                y: 80 + Math.floor(count / 3) * 180,
            },
            data: { config: defaultConfig(type) },
        };
        setNodes((nds) => [...nds, newNode]);
        setSelectedId(newId);
    };

    const onConnect = useCallback(
        (connection: Connection) => {
            const isTool = connection.sourceHandle === "out-tool";
            setEdges((eds) =>
                addEdge(
                    {
                        ...connection,
                        animated: isTool,
                        style: isTool
                            ? { stroke: "#6366f1", strokeDasharray: "4 3" }
                            : { stroke: "#3b82f6" },
                        label: isTool ? "tool" : undefined,
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
            }),
        ),
        is_active: true,
    });

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

    const handleExecute = async () => {
        if (!isEditing) {
            alert("Сохрани workflow перед запуском");
            return;
        }
        setShowRunDialog(true);
    };

    const confirmExecute = async () => {
        setShowRunDialog(false);
        setRunStatus("Выполняется...");
        const { data, error } = await api.executeWorkflow(Number(id), {
            input: runInput,
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
                    triggerInput: runInput,
                    logs: execData.logs || [],
                });
                setShowAiChat(false);
                setShowLog(true);
            }
        }
        if (error) setRunStatus(`Ошибка: ${error}`);
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
                                fitViewOptions={{ maxZoom: 1, padding: 0.4 }}
                                minZoom={0.2}
                            >
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
                        <AiChatPanel />
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

                {showRunDialog && (
                    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
                        <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5">
                            <h3 className="text-sm font-semibold text-gray-800 mb-1">
                                Тестовый запуск
                            </h3>
                            <p className="text-xs text-gray-400 mb-3">
                                Это значение попадёт в {"{input}"} — например,
                                вопрос пользователя.
                            </p>
                            <textarea
                                autoFocus
                                value={runInput}
                                onChange={(e) => setRunInput(e.target.value)}
                                rows={3}
                                placeholder="Где мой заказ 5?"
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            />
                            <div className="flex justify-end gap-2 mt-4">
                                <button
                                    onClick={() => setShowRunDialog(false)}
                                    className="px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 rounded-lg"
                                >
                                    Отмена
                                </button>
                                <button
                                    onClick={confirmExecute}
                                    className="px-4 py-1.5 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium"
                                >
                                    Запустить
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
