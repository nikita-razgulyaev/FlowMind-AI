import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Save, Play, Plus, Trash2, Cloud, Server } from "lucide-react";
import { api } from "../api/client";
import type { WorkflowNode, WorkflowEdge } from "../types/workflow";

const NODE_TYPES = [
    { type: "manual", label: "Manual Trigger", color: "bg-green-100 text-green-700" },
    { type: "schedule", label: "Schedule", color: "bg-purple-100 text-purple-700" },
    { type: "llm", label: "AI / LLM", color: "bg-blue-100 text-blue-700" },
    { type: "http", label: "HTTP Request", color: "bg-orange-100 text-orange-700" },
    { type: "condition", label: "Condition", color: "bg-yellow-100 text-yellow-700" },
    { type: "print", label: "Print Output", color: "bg-gray-100 text-gray-700" },
];

// Модели для разных режимов
const LLM_MODELS = {
    local: [
        { value: "llama3", label: "Llama 3 (Ollama)" },
        { value: "mistral", label: "Mistral (Ollama)" },
        { value: "phi3", label: "Phi-3 (Ollama)" },
    ],
    cloud: [
        { value: "Qwen/Qwen2.5-1.5B-Instruct", label: "Qwen 1.5B (Hugging Face)" },
        { value: "Qwen/Qwen2.5-7B-Instruct", label: "Qwen 7B (Hugging Face)" },
        { value: "google/gemma-2-2b-it", label: "Gemma 2B (Hugging Face)" },
        { value: "microsoft/Phi-3-mini-4k-instruct", label: "Phi-3 (Hugging Face)" },
    ]
};

export default function WorkflowEditor() {
    const { id } = useParams();
    const navigate = useNavigate();
    const isEditing = !!id;

    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [nodes, setNodes] = useState<WorkflowNode[]>([]);
    const [edges, setEdges] = useState<WorkflowEdge[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    
    // Cloud (API) по умолчанию
    const [llmMode, setLlmMode] = useState<"local" | "cloud">("cloud");

    useEffect(() => {
        if (isEditing) {
            loadWorkflow();
        }
    }, [id]);

    // Обновляем модели всех LLM-узлов при смене режима (только ручное переключение)
    useEffect(() => {
        // Пропускаем первый рендер (при загрузке workflow уже мигрировано в loadWorkflow)
        if (nodes.length === 0) return;

        setNodes(prevNodes => prevNodes.map(node => {
            if (node.type === "llm") {
                const newModel = llmMode === "cloud"
                    ? "Qwen/Qwen2.5-1.5B-Instruct"
                    : "llama3";
                return { 
                    ...node, 
                    config: { 
                        ...node.config, 
                        model: newModel, 
                        mode: llmMode 
                    } 
                };
            }
            return node;
        }));
    }, [llmMode]);

    const loadWorkflow = async () => {
        const { data } = await api.getWorkflow(Number(id));
        if (data) {
            setName(data.name);
            setDescription(data.description);

            // Определяем llmMode из первого LLM-узла
            const firstLlm = data.nodes.find((n: any) => n.type === "llm");
            const savedMode = firstLlm?.config?.mode as "local" | "cloud" | undefined;
            const detectedMode = savedMode || "cloud";
            setLlmMode(detectedMode);

            // Мигрируем модели если режим не совпадает с сохранённой моделью
            const migratedNodes = data.nodes.map((node: any) => {
                if (node.type === "llm") {
                    const nodeMode = node.config?.mode || detectedMode;
                    const isLocalModel = ["llama3", "mistral", "phi3"].includes(node.config?.model);
                    const isCloudModel = node.config?.model?.includes("/");

                    // Если режим cloud, но модель локальная — заменяем
                    if (nodeMode === "cloud" && isLocalModel) {
                        return {
                            ...node,
                            config: {
                                ...node.config,
                                model: "Qwen/Qwen2.5-1.5B-Instruct",
                                mode: "cloud"
                            }
                        };
                    }
                    // Если режим local, но модель облачная — заменяем
                    if (nodeMode === "local" && isCloudModel) {
                        return {
                            ...node,
                            config: {
                                ...node.config,
                                model: "llama3",
                                mode: "local"
                            }
                        };
                    }
                }
                return node;
            });

            setNodes(migratedNodes);
            setEdges(data.edges);
        }
    };

    const addNode = (type: string) => {
        const defaultModel = llmMode === "cloud" 
            ? "Qwen/Qwen2.5-1.5B-Instruct" 
            : "llama3";
            
        const newNode: WorkflowNode = {
            id: `node_${Date.now()}`,
            type: type as any,
            config:
                type === "llm"
                    ? { 
                        model: defaultModel, 
                        prompt: "", 
                        temperature: 0.7,
                        mode: llmMode  // ← сохраняем режим в конфиг
                      }
                    : type === "http"
                      ? { method: "GET", url: "" }
                      : type === "print"
                        ? { value: "" }
                        : {},
        };
        setNodes([...nodes, newNode]);
    };

    const updateNodeConfig = (nodeId: string, config: Record<string, any>) => {
        setNodes(nodes.map((n) => (n.id === nodeId ? { ...n, config } : n)));
    };

    const removeNode = (nodeId: string) => {
        setNodes(nodes.filter((n) => n.id !== nodeId));
        setEdges(edges.filter((e) => e.from_node !== nodeId && e.to_node !== nodeId));
    };

    const addEdge = (from: string, to: string) => {
        const newEdge: WorkflowEdge = {
            id: `edge_${Date.now()}`,
            from_node: from,
            to_node: to,
        };
        setEdges([...edges, newEdge]);
    };

    const handleSave = async () => {
        setIsLoading(true);

        const workflow = {
            name,
            description,
            nodes,
            edges,
            is_active: true,
        };

        const { data, error } = await api.createWorkflow(workflow);
        if (data) {
            navigate(`/workflow/${data.id}`);
        }
        if (error) alert(`Error: ${error}`);

        setIsLoading(false);
    };

    const handleExecute = async () => {
        if (!isEditing) {
            alert("Save workflow first");
            return;
        }
        const { data, error } = await api.executeWorkflow(Number(id));
        if (data) {
            alert(`Started! Execution ID: ${data.execution_id}`);
        }
        if (error) alert(`Error: ${error}`);
    };

    // Получаем список моделей для текущего режима
    const currentModels = LLM_MODELS[llmMode];

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900">
                        {isEditing ? "Edit Workflow" : "New Workflow"}
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Mode: <span className="font-medium text-blue-600">{llmMode}</span>
                    </p>
                </div>
                <div className="flex gap-3">
                    {/* Кнопка переключения режима */}
                    <button
                        onClick={() => setLlmMode(llmMode === "local" ? "cloud" : "local")}
                        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
                            llmMode === "cloud" 
                                ? "bg-purple-100 text-purple-700 hover:bg-purple-200" 
                                : "bg-green-100 text-green-700 hover:bg-green-200"
                        }`}
                    >
                        {llmMode === "cloud" ? <Cloud className="w-4 h-4" /> : <Server className="w-4 h-4" />}
                        {llmMode === "local" ? "Switch to Cloud" : "Switch to Local"}
                    </button>
                    <button
                        onClick={handleExecute}
                        disabled={!isEditing}
                        className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                    >
                        <Play className="w-4 h-4" />
                        Run
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={isLoading}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                    >
                        <Save className="w-4 h-4" />
                        {isLoading ? "Saving..." : "Save"}
                    </button>
                </div>
            </div>

            <div className="bg-white p-6 rounded-xl border border-gray-200 space-y-4">
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                        Name
                    </label>
                    <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                        placeholder="My AI Workflow"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                        Description
                    </label>
                    <textarea
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                        rows={2}
                        placeholder="What does this workflow do?"
                    />
                </div>
            </div>

            <div className="bg-white p-6 rounded-xl border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    Add Blocks
                </h3>
                <div className="flex flex-wrap gap-2">
                    {NODE_TYPES.map((nodeType) => (
                        <button
                            key={nodeType.type}
                            onClick={() => addNode(nodeType.type)}
                            className={`px-4 py-2 rounded-lg text-sm font-medium ${nodeType.color} hover:opacity-80`}
                        >
                            <Plus className="w-4 h-4 inline mr-1" />
                            {nodeType.label}
                        </button>
                    ))}
                </div>
            </div>

            <div className="bg-white p-6 rounded-xl border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    Workflow Steps
                </h3>

                {nodes.length === 0 ? (
                    <p className="text-gray-500 text-center py-8">
                        Add blocks to build your workflow
                    </p>
                ) : (
                    <div className="space-y-4">
                        {nodes.map((node, index) => (
                            <div
                                key={node.id}
                                className="border border-gray-200 rounded-lg p-4"
                            >
                                <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-3">
                                        <span className="w-8 h-8 bg-gray-100 rounded-full flex items-center justify-center text-sm font-bold text-gray-600">
                                            {index + 1}
                                        </span>
                                        <span className="font-medium text-gray-900 capitalize">
                                            {node.type}
                                        </span>
                                        <span className="text-xs text-gray-400 font-mono">
                                            {node.id}
                                        </span>
                                        {node.type === "llm" && node.config.mode && (
                                            <span className={`text-xs px-2 py-0.5 rounded-full ${
                                                node.config.mode === "cloud" 
                                                    ? "bg-purple-100 text-purple-700" 
                                                    : "bg-green-100 text-green-700"
                                            }`}>
                                                {node.config.mode}
                                            </span>
                                        )}
                                    </div>
                                    <button
                                        onClick={() => removeNode(node.id)}
                                        className="text-red-400 hover:text-red-600"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>

                                <div className="pl-11 space-y-3">
                                    {node.type === "llm" && (
                                        <>
                                            <div>
                                                <label className="text-xs text-gray-500">
                                                    Model ({node.config.mode || llmMode})
                                                </label>
                                                <select
                                                    value={node.config.model}
                                                    onChange={(e) =>
                                                        updateNodeConfig(
                                                            node.id,
                                                            {
                                                                ...node.config,
                                                                model: e.target.value,
                                                            },
                                                        )
                                                    }
                                                    className="w-full mt-1 px-3 py-2 border rounded-md text-sm"
                                                >
                                                    {currentModels.map((model) => (
                                                        <option key={model.value} value={model.value}>
                                                            {model.label}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="text-xs text-gray-500">
                                                    Prompt
                                                </label>
                                                <textarea
                                                    value={node.config.prompt}
                                                    onChange={(e) =>
                                                        updateNodeConfig(
                                                            node.id,
                                                            {
                                                                ...node.config,
                                                                prompt: e.target.value,
                                                            },
                                                        )
                                                    }
                                                    className="w-full mt-1 px-3 py-2 border rounded-md text-sm font-mono"
                                                    rows={3}
                                                    placeholder="Enter prompt... Use {input} for trigger data"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-xs text-gray-500">
                                                    Temperature: {node.config.temperature}
                                                </label>
                                                <input
                                                    type="range"
                                                    min="0"
                                                    max="2"
                                                    step="0.1"
                                                    value={node.config.temperature}
                                                    onChange={(e) =>
                                                        updateNodeConfig(
                                                            node.id,
                                                            {
                                                                ...node.config,
                                                                temperature: parseFloat(e.target.value),
                                                            },
                                                        )
                                                    }
                                                    className="w-full mt-1"
                                                />
                                            </div>
                                        </>
                                    )}

                                    {node.type === "http" && (
                                        <>
                                            <div>
                                                <label className="text-xs text-gray-500">
                                                    Method
                                                </label>
                                                <select
                                                    value={node.config.method}
                                                    onChange={(e) =>
                                                        updateNodeConfig(
                                                            node.id,
                                                            {
                                                                ...node.config,
                                                                method: e.target.value,
                                                            },
                                                        )
                                                    }
                                                    className="w-full mt-1 px-3 py-2 border rounded-md text-sm"
                                                >
                                                    <option>GET</option>
                                                    <option>POST</option>
                                                </select>
                                            </div>
                                            <div>
                                                <label className="text-xs text-gray-500">
                                                    URL
                                                </label>
                                                <input
                                                    type="text"
                                                    value={node.config.url}
                                                    onChange={(e) =>
                                                        updateNodeConfig(
                                                            node.id,
                                                            {
                                                                ...node.config,
                                                                url: e.target.value,
                                                            },
                                                        )
                                                    }
                                                    className="w-full mt-1 px-3 py-2 border rounded-md text-sm font-mono"
                                                    placeholder="https://api.example.com/data"
                                                />
                                            </div>
                                        </>
                                    )}

                                    {node.type === "print" && (
                                        <div>
                                            <label className="text-xs text-gray-500">
                                                Value (use {"{node_id}"} for variables)
                                            </label>
                                            <input
                                                type="text"
                                                value={node.config.value}
                                                onChange={(e) =>
                                                    updateNodeConfig(node.id, {
                                                        ...node.config,
                                                        value: e.target.value,
                                                    })
                                                }
                                                className="w-full mt-1 px-3 py-2 border rounded-md text-sm font-mono"
                                                placeholder="Result: {llm_node}"
                                            />
                                        </div>
                                    )}

                                    {node.type === "condition" && (
                                        <div>
                                            <label className="text-xs text-gray-500">
                                                Expression (Python eval)
                                            </label>
                                            <input
                                                type="text"
                                                value={node.config.expression || ""}
                                                onChange={(e) =>
                                                    updateNodeConfig(node.id, {
                                                        ...node.config,
                                                        expression: e.target.value,
                                                    })
                                                }
                                                className="w-full mt-1 px-3 py-2 border rounded-md text-sm font-mono"
                                                placeholder="{result} > 0.5"
                                            />
                                        </div>
                                    )}
                                </div>

                                {index < nodes.length - 1 && (
                                    <div className="pl-11 mt-3">
                                        <select
                                            onChange={(e) =>
                                                e.target.value && addEdge(node.id, e.target.value)
                                            }
                                            className="text-sm border rounded-md px-3 py-1"
                                            defaultValue=""
                                        >
                                            <option value="">Connect to...</option>
                                            {nodes.slice(index + 1).map((n) => (
                                                <option key={n.id} value={n.id}>
                                                    {n.type} ({n.id})
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="bg-gray-900 p-6 rounded-xl">
                <h3 className="text-lg font-semibold text-white mb-4">
                    JSON Preview
                </h3>
                <pre className="text-green-400 text-sm overflow-auto">
                    {JSON.stringify({ name, description, nodes, edges }, null, 2)}
                </pre>
            </div>
        </div>
    );
}