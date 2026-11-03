import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import { api } from "../api/client";
import type { Workflow } from "../types/workflow";
import EditorSidebar from "../components/canvas/EditorSidebar";
import { NODE_META } from "../components/canvas/CanvasNode";

export default function WorkflowList() {
    const navigate = useNavigate();
    const [workflows, setWorkflows] = useState<Workflow[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [selected, setSelected] = useState<Set<number>>(new Set());
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [deleting, setDeleting] = useState(false);

    useEffect(() => {
        load();
    }, []);

    const load = async () => {
        setIsLoading(true);
        const { data } = await api.getWorkflows();
        if (data) setWorkflows(data);
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
        if (selected.size === workflows.length) setSelected(new Set());
        else setSelected(new Set(workflows.map((w) => w.id)));
    };

    const handleDeleteOne = async (e: React.MouseEvent, id: number) => {
        e.preventDefault();
        e.stopPropagation();
        setSelected(new Set([id]));
        setConfirmOpen(true);
    };

    const confirmDelete = async () => {
        const ids = Array.from(selected);
        if (!ids.length) return;
        setDeleting(true);
        const { error } = await api.bulkDeleteWorkflows(ids);
        setDeleting(false);
        setConfirmOpen(false);
        if (error) {
            alert(`Ошибка: ${error}`);
            return;
        }
        setWorkflows((wfs) => wfs.filter((w) => !selected.has(w.id)));
        setSelected(new Set());
    };

    const allSelected = workflows.length > 0 && selected.size === workflows.length;

    return (
        <div className="flex h-screen">
            <EditorSidebar />
            <div className="flex-1 overflow-y-auto bg-gray-50">
                <div className="max-w-4xl mx-auto px-8 py-10">
                    <div className="flex items-center justify-between mb-8">
                        <div>
                            <h1 className="text-2xl font-bold text-gray-900">Воркфлоу</h1>
                            <p className="text-sm text-gray-500 mt-1">
                                Все твои автоматизации и AI-агенты
                            </p>
                        </div>
                        <div className="flex items-center gap-2">
                            {selected.size > 0 && (
                                <button
                                    onClick={() => setConfirmOpen(true)}
                                    className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium"
                                >
                                    <Trash2 className="w-4 h-4" />
                                    Удалить ({selected.size})
                                </button>
                            )}
                            <button
                                onClick={() => navigate("/workflow/new")}
                                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                            >
                                <Plus className="w-4 h-4" /> Новый workflow
                            </button>
                        </div>
                    </div>

                    {isLoading ? (
                        <p className="text-sm text-gray-400">Загрузка...</p>
                    ) : workflows.length === 0 ? (
                        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
                            <p className="text-gray-500 mb-4">Пока нет ни одного workflow</p>
                            <button
                                onClick={() => navigate("/workflow/new")}
                                className="text-blue-600 hover:underline text-sm font-medium"
                            >
                                Создать первый →
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            <div className="flex items-center gap-3 px-1">
                                <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
                                    <input
                                        type="checkbox"
                                        checked={allSelected}
                                        onChange={toggleAll}
                                        className="rounded border-gray-300"
                                    />
                                    {allSelected ? "Снять выделение" : "Выбрать все"}
                                </label>
                                {selected.size > 0 && (
                                    <span className="text-xs text-gray-400">
                                        выбрано: {selected.size}
                                    </span>
                                )}
                            </div>

                            {workflows.map((wf) => {
                                const isSel = selected.has(wf.id);
                                return (
                                    <div
                                        key={wf.id}
                                        className={`flex items-stretch gap-0 bg-white rounded-xl border transition-colors ${
                                            isSel
                                                ? "border-blue-400 ring-1 ring-blue-200"
                                                : "border-gray-200 hover:border-blue-300"
                                        }`}
                                    >
                                        <label
                                            className="flex items-center px-4 cursor-pointer"
                                            onClick={(e) => e.stopPropagation()}
                                        >
                                            <input
                                                type="checkbox"
                                                checked={isSel}
                                                onChange={() => toggle(wf.id)}
                                                className="rounded border-gray-300"
                                            />
                                        </label>
                                        <Link
                                            to={`/workflow/${wf.id}`}
                                            className="flex-1 min-w-0 p-5 pl-0"
                                        >
                                            <div className="flex items-center justify-between gap-3">
                                                <div className="min-w-0">
                                                    <p className="font-semibold text-gray-900 truncate">
                                                        {wf.name || "Без названия"}
                                                    </p>
                                                    {wf.description && (
                                                        <p className="text-sm text-gray-500 mt-0.5 truncate">
                                                            {wf.description}
                                                        </p>
                                                    )}
                                                    <div className="flex gap-1.5 mt-2 flex-wrap">
                                                        {wf.nodes.map((n) => {
                                                            const meta =
                                                                NODE_META[n.type] ?? NODE_META.print;
                                                            return (
                                                                <span
                                                                    key={n.id}
                                                                    className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${meta.badge}`}
                                                                >
                                                                    {meta.label}
                                                                </span>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                                <button
                                                    onClick={(e) => handleDeleteOne(e, wf.id)}
                                                    className="shrink-0 p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg"
                                                    title="Удалить"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </Link>
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
                        <h2 className="text-lg font-semibold text-gray-900">Удалить воркфлоу?</h2>
                        <p className="text-sm text-gray-600 mt-2">
                            {selected.size === 1
                                ? "Воркфлоу и вся его история выполнений будут удалены безвозвратно."
                                : `Будет удалено воркфлоу: ${selected.size}. История выполнений по ним тоже удалится.`}
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
