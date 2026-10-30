import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
    CheckCircle2,
    XCircle,
    Loader2,
    ChevronDown,
    ExternalLink,
    Trash2,
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
    const [selected, setSelected] = useState<Set<number>>(new Set());
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [deleting, setDeleting] = useState(false);

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
        setSelected(new Set());
        setIsLoading(false);
    };

    const toggle = (id: number) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const toggleAll = () => {
        if (selected.size === executions.length) setSelected(new Set());
        else setSelected(new Set(executions.map((e) => e.id)));
    };

    const confirmDelete = async () => {
        const ids = Array.from(selected);
        if (!ids.length) return;
        setDeleting(true);
        const { error } = await api.bulkDeleteExecutions(ids);
        setDeleting(false);
        setConfirmOpen(false);
        if (error) {
            alert(`Ошибка: ${error}`);
            return;
        }
        setExecutions((list) => list.filter((e) => !selected.has(e.id)));
        setSelected(new Set());
        if (expandedId && selected.has(expandedId)) setExpandedId(null);
    };

    const allSelected =
        executions.length > 0 && selected.size === executions.length;

    return (
        <div className="flex h-screen">
            <EditorSidebar />
            <div className="flex-1 overflow-y-auto bg-gray-50">
                <div className="max-w-4xl mx-auto px-8 py-10">
                    <div className="flex items-center justify-between mb-2">
                        <h1 className="text-2xl font-bold text-gray-900">
                            История выполнений
                        </h1>
                        {selected.size > 0 && (
                            <button
                                onClick={() => setConfirmOpen(true)}
                                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium"
                            >
                                <Trash2 className="w-4 h-4" />
                                Удалить ({selected.size})
                            </button>
                        )}
                    </div>
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
                            <div className="flex items-center gap-3 px-1 mb-1">
                                <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
                                    <input
                                        type="checkbox"
                                        checked={allSelected}
                                        onChange={toggleAll}
                                        className="rounded border-gray-300"
                                    />
                                    {allSelected
                                        ? "Снять выделение"
                                        : "Выбрать все"}
                                </label>
                                {selected.size > 0 && (
                                    <span className="text-xs text-gray-400">
                                        выбрано: {selected.size}
                                    </span>
                                )}
                            </div>

                            {executions.map((ex) => {
                                const meta =
                                    STATUS_META[ex.status] ||
                                    STATUS_META.running;
                                const StatusIcon = meta.icon;
                                const isOpen = expandedId === ex.id;
                                const isSel = selected.has(ex.id);
                                const triggerInput = extractTriggerInput(
                                    ex.trigger_data,
                                );
                                const lines = isOpen
                                    ? buildLines(triggerInput, ex.logs || [])
                                    : [];

                                return (
                                    <div
                                        key={ex.id}
                                        className={`bg-white rounded-xl border overflow-hidden ${
                                            isSel
                                                ? "border-blue-400 ring-1 ring-blue-200"
                                                : "border-gray-200"
                                        }`}
                                    >
                                        <div className="flex items-center">
                                            <label
                                                className="flex items-center px-3 py-3 cursor-pointer"
                                                onClick={(e) =>
                                                    e.stopPropagation()
                                                }
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={isSel}
                                                    onChange={() =>
                                                        toggle(ex.id)
                                                    }
                                                    className="rounded border-gray-300"
                                                />
                                            </label>
                                            <button
                                                onClick={() =>
                                                    setExpandedId(
                                                        isOpen ? null : ex.id,
                                                    )
                                                }
                                                className="flex-1 flex items-center gap-3 pr-4 py-3 text-left hover:bg-gray-50 min-w-0"
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
                                        </div>

                                        {isOpen && (
                                            <div className="border-t border-gray-100 px-4 py-3 space-y-1.5 bg-gray-50/50">
                                                {lines.length === 0 && (
                                                    <p className="text-xs text-gray-400">
                                                        Нет логов
                                                    </p>
                                                )}
                                                {lines.map((line, i) => (
                                                    <div
                                                        key={i}
                                                        className="text-xs font-mono text-gray-700 whitespace-pre-wrap break-words"
                                                    >
                                                        {line}
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

            {confirmOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
                    <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
                        <h2 className="text-lg font-semibold text-gray-900">
                            Удалить записи истории?
                        </h2>
                        <p className="text-sm text-gray-600 mt-2">
                            {selected.size === 1
                                ? "Запись выполнения будет удалена безвозвратно."
                                : `Будет удалено записей: ${selected.size}. Действие нельзя отменить.`}
                        </p>
                        <div className="flex justify-end gap-2 mt-6">
                            <button
                                onClick={() => setConfirmOpen(false)}
                                disabled={deleting}
                                className="px-4 py-2 text-sm rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50"
                            >
                                Отмена
                            </button>
                            <button
                                onClick={confirmDelete}
                                disabled={deleting}
                                className="px-4 py-2 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
                            >
                                {deleting ? "Удаление..." : "Удалить"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
