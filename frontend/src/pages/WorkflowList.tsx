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

    useEffect(() => {
        load();
    }, []);

    const load = async () => {
        setIsLoading(true);
        const { data } = await api.getWorkflows();
        if (data) setWorkflows(data);
        setIsLoading(false);
    };

    const handleDelete = async (e: React.MouseEvent, id: number) => {
        e.preventDefault();
        e.stopPropagation();
        if (!confirm("Удалить этот workflow насовсем?")) return;
        const { error } = await api.deleteWorkflow(id);
        if (error) {
            alert(`Ошибка: ${error}`);
            return;
        }
        setWorkflows((wfs) => wfs.filter((w) => w.id !== id));
    };

    return (
        <div className="flex h-screen">
            <EditorSidebar />
            <div className="flex-1 overflow-y-auto bg-gray-50">
                <div className="max-w-4xl mx-auto px-8 py-10">
                    <div className="flex items-center justify-between mb-8">
                        <div>
                            <h1 className="text-2xl font-bold text-gray-900">
                                Воркфлоу
                            </h1>
                            <p className="text-sm text-gray-500 mt-1">
                                Все твои автоматизации и AI-агенты
                            </p>
                        </div>
                        <button
                            onClick={() => navigate("/workflow/new")}
                            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                        >
                            <Plus className="w-4 h-4" /> Новый workflow
                        </button>
                    </div>

                    {isLoading ? (
                        <p className="text-sm text-gray-400">Загрузка...</p>
                    ) : workflows.length === 0 ? (
                        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
                            <p className="text-gray-500 mb-4">
                                Пока нет ни одного workflow
                            </p>
                            <button
                                onClick={() => navigate("/workflow/new")}
                                className="text-blue-600 hover:underline text-sm font-medium"
                            >
                                Создать первый →
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {workflows.map((wf) => (
                                <Link
                                    key={wf.id}
                                    to={`/workflow/${wf.id}`}
                                    className="block bg-white p-5 rounded-xl border border-gray-200 hover:border-blue-300 transition-colors"
                                >
                                    <div className="flex items-center justify-between">
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
                                                        NODE_META[n.type] ??
                                                        NODE_META.print;
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
                                        <div className="flex items-center gap-3 shrink-0 ml-4">
                                            <span className="text-xs text-gray-400">
                                                {new Date(
                                                    wf.created_at,
                                                ).toLocaleDateString()}
                                            </span>
                                            <button
                                                onClick={(e) =>
                                                    handleDelete(e, wf.id)
                                                }
                                                className="p-1.5 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded"
                                                title="Удалить"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
