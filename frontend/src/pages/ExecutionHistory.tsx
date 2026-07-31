import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
    CheckCircle2,
    XCircle,
    Loader2,
    ChevronDown,
    ExternalLink,
} from "lucide-react";
import { api } from "../api/client";
import type { Workflow } from "../types/workflow";
import EditorSidebar from "../components/canvas/EditorSidebar";
import {
    buildLines,
    extractTriggerInput,
    type LogEntry,
} from "../utils/executionLog";

interface Execution {
    id: number;
    workflow_id: number;
    status: string;
    trigger_data: Record<string, any> | null;
    logs: LogEntry[] | null;
    started_at: string;
    finished_at: string | null;
}

const STATUS_META: Record<
    string,
    { icon: typeof CheckCircle2; color: string; label: string }
> = {
    success: {
        icon: CheckCircle2,
        color: "text-emerald-600 bg-emerald-50",
        label: "success",
    },
    failed: { icon: XCircle, color: "text-red-600 bg-red-50", label: "failed" },
    running: {
        icon: Loader2,
        color: "text-blue-600 bg-blue-50",
        label: "running",
    },
};

function formatDate(iso: string): string {
    try {
        return new Date(iso).toLocaleString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return iso;
    }
}

export default function ExecutionHistory() {
    const [executions, setExecutions] = useState<Execution[]>([]);
    const [workflowNames, setWorkflowNames] = useState<Record<number, string>>(
        {},
    );
    const [isLoading, setIsLoading] = useState(true);
    const [expandedId, setExpandedId] = useState<number | null>(null);

    useEffect(() => {
        load();
    }, []);

    const load = async () => {
        setIsLoading(true);
        const [{ data: execData }, { data: wfData }] = await Promise.all([
            api.getExecutions(),
            api.getWorkflows(),
        ]);
        if (execData) {
            setExecutions(
                [...execData].sort((a, b) =>
                    a.started_at < b.started_at ? 1 : -1,
                ),
            );
        }
        if (wfData) {
            const map: Record<number, string> = {};
            for (const wf of wfData as Workflow[])
                map[wf.id] = wf.name || `Workflow #${wf.id}`;
            setWorkflowNames(map);
        }
        setIsLoading(false);
    };

    return (
        <div className="flex h-screen">
            <EditorSidebar />
            <div className="flex-1 overflow-y-auto bg-gray-50">
                <div className="max-w-4xl mx-auto px-8 py-10">
                    <h1 className="text-2xl font-bold text-gray-900">
                        История выполнений
                    </h1>
                    <p className="text-sm text-gray-500 mt-1 mb-8">
                        Все запуски по всем воркфлоу
                    </p>

                    {isLoading ? (
                        <p className="text-sm text-gray-400">Загрузка...</p>
                    ) : executions.length === 0 ? (
                        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-500">
                            Пока нет ни одного запуска
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {executions.map((ex) => {
                                const meta =
                                    STATUS_META[ex.status] ||
                                    STATUS_META.running;
                                const StatusIcon = meta.icon;
                                const isOpen = expandedId === ex.id;
                                const triggerInput = extractTriggerInput(
                                    ex.trigger_data,
                                );
                                const lines = isOpen
                                    ? buildLines(triggerInput, ex.logs || [])
                                    : [];

                                return (
                                    <div
                                        key={ex.id}
                                        className="bg-white rounded-xl border border-gray-200 overflow-hidden"
                                    >
                                        <button
                                            onClick={() =>
                                                setExpandedId(
                                                    isOpen ? null : ex.id,
                                                )
                                            }
                                            className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50"
                                        >
                                            <span
                                                className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${meta.color}`}
                                            >
                                                <StatusIcon
                                                    className={`w-4 h-4 ${ex.status === "running" ? "animate-spin" : ""}`}
                                                />
                                            </span>
                                            <div className="min-w-0 flex-1">
                                                <p className="text-sm font-medium text-gray-800 truncate">
                                                    {workflowNames[
                                                        ex.workflow_id
                                                    ] ||
                                                        `Workflow #${ex.workflow_id}`}
                                                    <span className="text-gray-400 font-normal">
                                                        {" "}
                                                        · execution #{ex.id}
                                                    </span>
                                                </p>
                                                {triggerInput && (
                                                    <p className="text-xs text-gray-400 truncate mt-0.5">
                                                        {triggerInput}
                                                    </p>
                                                )}
                                            </div>
                                            <span className="text-xs text-gray-400 shrink-0">
                                                {formatDate(ex.started_at)}
                                            </span>
                                            <Link
                                                to={`/workflow/${ex.workflow_id}`}
                                                onClick={(e) =>
                                                    e.stopPropagation()
                                                }
                                                className="p-1.5 text-gray-300 hover:text-blue-500 hover:bg-blue-50 rounded shrink-0"
                                                title="Открыть workflow"
                                            >
                                                <ExternalLink className="w-3.5 h-3.5" />
                                            </Link>
                                            <ChevronDown
                                                className={`w-4 h-4 text-gray-300 shrink-0 transition-transform ${isOpen ? "rotate-180" : ""}`}
                                            />
                                        </button>

                                        {isOpen && (
                                            <div className="border-t border-gray-100 px-4 py-3 space-y-1.5 bg-gray-50/50">
                                                {lines.length === 0 && (
                                                    <p className="text-xs text-gray-400">
                                                        Нет читаемых шагов для
                                                        этого запуска.
                                                    </p>
                                                )}
                                                {lines.map((line, i) => (
                                                    <div
                                                        key={i}
                                                        className="text-xs"
                                                    >
                                                        <span
                                                            className={
                                                                line.tone ===
                                                                "agent"
                                                                    ? "text-indigo-700 font-medium"
                                                                    : line.tone ===
                                                                        "tool"
                                                                      ? "text-emerald-700 font-medium"
                                                                      : line.tone ===
                                                                          "user"
                                                                        ? "text-gray-500"
                                                                        : "text-gray-400"
                                                            }
                                                        >
                                                            {line.who}
                                                        </span>
                                                        <span className="text-gray-500">
                                                            :{" "}
                                                        </span>
                                                        <span className="text-gray-700">
                                                            {line.text}
                                                        </span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
