import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { api } from "../api/client";
import EditorSidebar from "../components/canvas/EditorSidebar";
import { NODE_META } from "../components/canvas/CanvasNode";

interface TemplateNode {
    id: string;
    type: string;
    config: Record<string, any>;
}

interface TemplateData {
    name: string;
    description: string;
    nodes: TemplateNode[];
    edges: any[];
    is_active: boolean;
}

const CATEGORIES: { id: string; label: string; keys: string[] }[] = [
    { id: "all", label: "Все", keys: [] },
    { id: "telegram", label: "Telegram", keys: ["telegram_support", "lead_to_sheets", "lead_qualification", "request_router", "faq_bot", "order_request"] },
    { id: "email", label: "Почта", keys: ["email_support", "email_leads", "email_router"] },
    { id: "other", label: "Другое", keys: ["meeting_summary"] },
];

function TemplatesByCategory({
    templates,
    creatingKey,
    onUse,
}: {
    templates: Record<string, TemplateData>;
    creatingKey: string | null;
    onUse: (key: string) => void;
}) {
    const [tab, setTab] = useState("all");
    const cat = CATEGORIES.find((c) => c.id === tab) ?? CATEGORIES[0];
    const entries = Object.entries(templates).filter(([key]) =>
        tab === "all" ? true : cat.keys.includes(key),
    );

    return (
        <div>
            <div className="flex flex-wrap gap-2 mb-6 border-b border-gray-200 pb-3">
                {CATEGORIES.map((c) => (
                    <button
                        key={c.id}
                        onClick={() => setTab(c.id)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                            tab === c.id
                                ? "bg-blue-600 text-white"
                                : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
                        }`}
                    >
                        {c.label}
                    </button>
                ))}
            </div>
            {entries.length === 0 ? (
                <p className="text-sm text-gray-400">В этой категории пока нет шаблонов</p>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {entries.map(([key, tpl]) => {
                        const typeCounts = new Map<string, number>();
                        for (const n of tpl.nodes)
                            typeCounts.set(n.type, (typeCounts.get(n.type) || 0) + 1);
                        return (
                            <div
                                key={key}
                                className="bg-white border border-gray-200 rounded-xl p-4 flex flex-col"
                            >
                                <div className="flex items-start gap-2 mb-1">
                                    <Sparkles className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                                    <h3 className="font-semibold text-gray-900">{tpl.name}</h3>
                                </div>
                                <p className="text-sm text-gray-400 flex-1">{tpl.description}</p>
                                <div className="flex items-center gap-1.5 mt-3 flex-wrap">
                                    {[...typeCounts.entries()].map(([type, count]) => {
                                        const meta = NODE_META[type];
                                        if (!meta) return null;
                                        return (
                                            <span
                                                key={type}
                                                className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${meta.badge}`}
                                            >
                                                {meta.label}
                                                {count > 1 ? ` ×${count}` : ""}
                                            </span>
                                        );
                                    })}
                                </div>
                                <button
                                    onClick={() => onUse(key)}
                                    disabled={creatingKey === key}
                                    className="mt-4 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
                                >
                                    {creatingKey === key ? "Создаём..." : "Использовать шаблон"}
                                </button>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

export default function Templates() {
    const navigate = useNavigate();
    const [templates, setTemplates] = useState<Record<
        string,
        TemplateData
    > | null>(null);
    const [creatingKey, setCreatingKey] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        load();
    }, []);

    const load = async () => {
        const { data, error } = await api.getTemplates();
        if (data) setTemplates(data);
        if (error) setError(error);
    };

    const handleUse = async (key: string) => {
        setCreatingKey(key);
        const { data, error } = await api.createFromTemplate(key);
        setCreatingKey(null);
        if (data) navigate(`/workflow/${data.id}`);
        if (error) alert(`Ошибка: ${error}`);
    };

    return (
        <div className="flex h-screen">
            <EditorSidebar />
            <div className="flex-1 overflow-y-auto bg-gray-50">
                <div className="max-w-4xl mx-auto px-8 py-10">
                    <h1 className="text-2xl font-bold text-gray-900">
                        Шаблоны
                    </h1>
                    <p className="text-sm text-gray-500 mt-1 mb-8">
                        Готовые сценарии — используйте как есть или доработайте на
                        рабочей области
                    </p>

                    {error && (
                        <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-4 py-3 mb-4">
                            {error}
                        </div>
                    )}

                    {!templates && !error && (
                        <p className="text-sm text-gray-400">Загрузка...</p>
                    )}

                    {templates && (
                        <TemplatesByCategory
                            templates={templates}
                            creatingKey={creatingKey}
                            onUse={handleUse}
                        />
                    )}
                </div>
            </div>
        </div>
    );
}
