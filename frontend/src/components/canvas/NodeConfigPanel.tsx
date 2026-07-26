import { X, Trash2 } from "lucide-react";
import type { WorkflowNode } from "../../types/workflow";
import { NODE_META } from "./CanvasNode";

const LLM_MODELS = {
    local: [
        { value: "qwen2.5", label: "Qwen 2.5 (Ollama)" },
        { value: "llama3.1", label: "Llama 3.1 (Ollama)" },
        { value: "mistral", label: "Mistral (Ollama)" },
    ],
    cloud: [
        {
            value: "Qwen/Qwen2.5-1.5B-Instruct",
            label: "Qwen 1.5B (Hugging Face)",
        },
        { value: "Qwen/Qwen2.5-7B-Instruct", label: "Qwen 7B (Hugging Face)" },
        { value: "google/gemma-2-2b-it", label: "Gemma 2B (Hugging Face)" },
    ],
};

const label = "block text-xs font-medium text-gray-500 mb-1";
const input =
    "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500";

interface Props {
    node: WorkflowNode;
    onChange: (config: Record<string, any>) => void;
    onDelete: () => void;
    onClose: () => void;
}

export default function NodeConfigPanel({
    node,
    onChange,
    onDelete,
    onClose,
}: Props) {
    const meta = NODE_META[node.type] ?? NODE_META.print;
    const cfg = node.config || {};
    const set = (patch: Record<string, any>) => onChange({ ...cfg, ...patch });

    return (
        <div className="w-96 shrink-0 bg-white border-l border-gray-200 h-full overflow-y-auto">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 sticky top-0 bg-white">
                <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${meta.badge}`}
                >
                    {meta.label}
                </span>
                <span className="text-xs font-mono text-gray-400">
                    {node.id}
                </span>
                <div className="ml-auto flex items-center gap-1">
                    <button
                        onClick={onDelete}
                        className="p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                    <button
                        onClick={onClose}
                        className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            </div>

            <div className="p-4 space-y-4">
                {node.type === "llm" && (
                    <>
                        <div className="flex gap-2">
                            {(["local", "cloud"] as const).map((m) => (
                                <button
                                    key={m}
                                    onClick={() =>
                                        set({
                                            mode: m,
                                            model: LLM_MODELS[m][0].value,
                                        })
                                    }
                                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium ${
                                        cfg.mode === m
                                            ? "bg-blue-600 text-white"
                                            : "bg-gray-100 text-gray-600"
                                    }`}
                                >
                                    {m === "local"
                                        ? "Local (Ollama)"
                                        : "Cloud (HF)"}
                                </button>
                            ))}
                        </div>
                        <div>
                            <label className={label}>Model</label>
                            <select
                                value={cfg.model || ""}
                                onChange={(e) => set({ model: e.target.value })}
                                className={input}
                            >
                                {LLM_MODELS[
                                    (cfg.mode as "local" | "cloud") || "cloud"
                                ].map((m) => (
                                    <option key={m.value} value={m.value}>
                                        {m.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className={label}>
                                Prompt (используй {"{input}"} или {"{node_id}"})
                            </label>
                            <textarea
                                value={cfg.prompt || ""}
                                onChange={(e) =>
                                    set({ prompt: e.target.value })
                                }
                                rows={4}
                                className={input}
                            />
                        </div>
                        <div>
                            <label className={label}>
                                Temperature: {cfg.temperature ?? 0.7}
                            </label>
                            <input
                                type="range"
                                min={0}
                                max={2}
                                step={0.1}
                                value={cfg.temperature ?? 0.7}
                                onChange={(e) =>
                                    set({
                                        temperature: parseFloat(e.target.value),
                                    })
                                }
                                className="w-full"
                            />
                        </div>
                    </>
                )}

                {node.type === "http" && (
                    <>
                        <div>
                            <label className={label}>Method</label>
                            <select
                                value={cfg.method || "GET"}
                                onChange={(e) =>
                                    set({ method: e.target.value })
                                }
                                className={input}
                            >
                                <option>GET</option>
                                <option>POST</option>
                            </select>
                        </div>
                        <div>
                            <label className={label}>
                                URL (можно с {"{param}"})
                            </label>
                            <input
                                value={cfg.url || ""}
                                onChange={(e) => set({ url: e.target.value })}
                                placeholder="https://api.example.com/orders/{order_id}"
                                className={input}
                            />
                        </div>
                        <div className="pt-2 border-t border-gray-100">
                            <p className="text-xs font-medium text-gray-500 mb-2">
                                Настройки инструмента (если нода подключена к
                                агенту)
                            </p>
                            <label className={label}>Tool name</label>
                            <input
                                value={cfg.tool_name || ""}
                                onChange={(e) =>
                                    set({ tool_name: e.target.value })
                                }
                                placeholder="get_order_status"
                                className={`${input} mb-2`}
                            />
                            <label className={label}>
                                Tool description (для модели)
                            </label>
                            <input
                                value={cfg.tool_description || ""}
                                onChange={(e) =>
                                    set({ tool_description: e.target.value })
                                }
                                placeholder="Получить статус заказа по ID"
                                className={`${input} mb-2`}
                            />
                            <label className={label}>
                                Parameters schema (JSON)
                            </label>
                            <textarea
                                value={
                                    typeof cfg.tool_parameters === "string"
                                        ? cfg.tool_parameters
                                        : JSON.stringify(
                                              cfg.tool_parameters ?? {
                                                  type: "object",
                                                  properties: {
                                                      order_id: {
                                                          type: "string",
                                                          description:
                                                              "ID заказа",
                                                      },
                                                  },
                                                  required: ["order_id"],
                                              },
                                              null,
                                              2,
                                          )
                                }
                                onChange={(e) => {
                                    try {
                                        set({
                                            tool_parameters: JSON.parse(
                                                e.target.value,
                                            ),
                                        });
                                    } catch {
                                        set({
                                            tool_parameters: e.target.value,
                                        });
                                    }
                                }}
                                rows={6}
                                className={input}
                            />
                        </div>
                    </>
                )}

                {node.type === "condition" && (
                    <div>
                        <label className={label}>
                            Expression (Python eval)
                        </label>
                        <input
                            value={cfg.expression || ""}
                            onChange={(e) =>
                                set({ expression: e.target.value })
                            }
                            placeholder="{http_1} > 0.5"
                            className={input}
                        />
                    </div>
                )}

                {node.type === "print" && (
                    <div>
                        <label className={label}>
                            Value (используй {"{node_id}"} для переменных)
                        </label>
                        <input
                            value={cfg.value || ""}
                            onChange={(e) => set({ value: e.target.value })}
                            placeholder="Result: {llm_1}"
                            className={input}
                        />
                    </div>
                )}

                {node.type === "agent" && (
                    <>
                        <div className="flex gap-2">
                            {(["local", "cloud"] as const).map((m) => (
                                <button
                                    key={m}
                                    onClick={() => set({ mode: m })}
                                    disabled={m === "cloud"}
                                    title={
                                        m === "cloud"
                                            ? "Пока поддерживается только local (Ollama)"
                                            : undefined
                                    }
                                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed ${
                                        (cfg.mode || "local") === m
                                            ? "bg-indigo-600 text-white"
                                            : "bg-gray-100 text-gray-600"
                                    }`}
                                >
                                    {m === "local"
                                        ? "Local (Ollama)"
                                        : "Cloud (пока нет)"}
                                </button>
                            ))}
                        </div>
                        <div>
                            <label className={label}>Model</label>
                            <input
                                value={cfg.model || "qwen2.5"}
                                onChange={(e) => set({ model: e.target.value })}
                                placeholder="qwen2.5"
                                className={input}
                            />
                        </div>
                        <div>
                            <label className={label}>System prompt</label>
                            <textarea
                                value={cfg.system_prompt || ""}
                                onChange={(e) =>
                                    set({ system_prompt: e.target.value })
                                }
                                rows={3}
                                placeholder="Ты — поддержка интернет-магазина."
                                className={input}
                            />
                        </div>
                        <div>
                            <label className={label}>
                                User prompt (обычно {"{input}"})
                            </label>
                            <input
                                value={cfg.prompt || "{input}"}
                                onChange={(e) =>
                                    set({ prompt: e.target.value })
                                }
                                className={input}
                            />
                        </div>
                        <div>
                            <label className={label}>
                                Max iterations: {cfg.max_iterations ?? 5}
                            </label>
                            <input
                                type="range"
                                min={1}
                                max={10}
                                step={1}
                                value={cfg.max_iterations ?? 5}
                                onChange={(e) =>
                                    set({
                                        max_iterations: parseInt(
                                            e.target.value,
                                        ),
                                    })
                                }
                                className="w-full"
                            />
                        </div>
                        <div>
                            <label className={label}>
                                Temperature: {cfg.temperature ?? 0.3} (ниже —
                                стабильнее tool calling)
                            </label>
                            <input
                                type="range"
                                min={0}
                                max={1}
                                step={0.1}
                                value={cfg.temperature ?? 0.3}
                                onChange={(e) =>
                                    set({
                                        temperature: parseFloat(e.target.value),
                                    })
                                }
                                className="w-full"
                            />
                        </div>
                        <p className="text-xs text-gray-400">
                            Инструменты подключаются связью с нижнего разъёма (↓
                            инструменты) к HTTP-ноде на canvas.
                        </p>
                    </>
                )}

                {(node.type === "manual" || node.type === "schedule") && (
                    <p className="text-xs text-gray-400">
                        У этого типа ноды пока нет настроек.
                    </p>
                )}
            </div>
        </div>
    );
}
