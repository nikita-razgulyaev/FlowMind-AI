import { useEffect, useState } from "react";
import { Plus, Trash2, X, Sparkles, Wrench } from "lucide-react";
import { api } from "../api/client";
import type { Connection } from "../types/workflow";
import EditorSidebar from "../components/canvas/EditorSidebar";
import { PROVIDERS, getProvider, type ProviderDef } from "../utils/providers";

const label = "block text-xs font-medium text-gray-500 mb-1";
const input =
    "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500";

function ConnectionModal({
    category,
    onClose,
    onCreated,
}: {
    category: "ai_api" | "tool";
    onClose: () => void;
    onCreated: (c: Connection) => void;
}) {
    const options = PROVIDERS.filter((p) => p.category === category);
    const [providerKey, setProviderKey] = useState(options[0]?.key || "");
    const [name, setName] = useState("");
    const [fields, setFields] = useState<Record<string, string>>({});
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const provider = getProvider(providerKey) as ProviderDef;

    const handleSubmit = async () => {
        if (!name.trim()) {
            setError("Укажи название подключения");
            return;
        }
        setSaving(true);
        setError(null);

        if (provider?.oauth) {
            const { data, error } = await api.startGoogleOAuth(
                providerKey,
                name.trim(),
            );
            setSaving(false);
            if (error) {
                setError(error);
                return;
            }
            if (data?.auth_url) {
                window.location.href = data.auth_url; // полный переход — иначе OAuth-редирект не сработает
            }
            return;
        }

        const { data, error } = await api.createConnection({
            category,
            provider: providerKey,
            name: name.trim(),
            config: fields,
        });
        setSaving(false);
        if (data) onCreated(data);
        if (error) setError(error);
    };

    return (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-gray-800">
                        Новое подключение
                    </h3>
                    <button
                        onClick={onClose}
                        className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                <div className="space-y-3">
                    <div>
                        <label className={label}>Провайдер</label>
                        <select
                            value={providerKey}
                            onChange={(e) => {
                                setProviderKey(e.target.value);
                                setFields({});
                            }}
                            className={input}
                        >
                            {options.map((p) => (
                                <option key={p.key} value={p.key}>
                                    {p.label}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className={label}>Название</label>
                        <input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="Например: Бот поддержки"
                            className={input}
                        />
                    </div>

                    {provider?.comingSoon ? (
                        <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                            {provider.note}
                        </p>
                    ) : provider?.oauth ? (
                        <p className="text-xs text-blue-600 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
                            Откроется окно входа Google — после согласия
                            подключение появится здесь автоматически.
                            {provider.note ? ` ${provider.note}.` : ""}
                        </p>
                    ) : (
                        provider?.fields.map((f) => (
                            <div key={f.key}>
                                <label className={label}>{f.label}</label>
                                <input
                                    type={f.type}
                                    value={fields[f.key] || ""}
                                    onChange={(e) =>
                                        setFields((cur) => ({
                                            ...cur,
                                            [f.key]: e.target.value,
                                        }))
                                    }
                                    placeholder={f.placeholder}
                                    className={input}
                                />
                            </div>
                        ))
                    )}

                    {provider?.note &&
                        !provider.comingSoon &&
                        !provider.oauth && (
                            <p className="text-xs text-gray-400">
                                {provider.note}
                            </p>
                        )}

                    {error && <p className="text-xs text-red-600">{error}</p>}
                </div>

                <div className="flex justify-end gap-2 mt-5">
                    <button
                        onClick={onClose}
                        className="px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 rounded-lg"
                    >
                        Отмена
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={saving || provider?.comingSoon}
                        className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                    >
                        {saving
                            ? "..."
                            : provider?.oauth
                              ? "Войти через Google"
                              : "Подключить"}
                    </button>
                </div>
            </div>
        </div>
    );
}

function ConnectionCard({
    conn,
    onDelete,
}: {
    conn: Connection;
    onDelete: (id: number) => void;
}) {
    const provider = getProvider(conn.provider);
    return (
        <div className="bg-white border border-gray-200 rounded-xl p-4 flex items-start justify-between gap-2">
            <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-900 truncate">
                    {conn.name}
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                    {provider?.label || conn.provider}
                </p>
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-2">
                    {Object.entries(conn.config).map(([k, v]) => (
                        <span
                            key={k}
                            className="text-[11px] font-mono text-gray-400"
                        >
                            {k}: {String(v)}
                        </span>
                    ))}
                </div>
                {provider?.usedFor && (
                    <p className="text-[11px] text-indigo-500 mt-2">
                        Используется для: {provider.usedFor}
                    </p>
                )}
            </div>
            <button
                onClick={() => onDelete(conn.id)}
                className="p-1.5 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded shrink-0"
            >
                <Trash2 className="w-4 h-4" />
            </button>
        </div>
    );
}

function CategorySection({
    title,
    icon: Icon,
    category,
    connections,
    onDelete,
    onOpenModal,
}: {
    title: string;
    icon: typeof Sparkles;
    category: "ai_api" | "tool";
    connections: Connection[];
    onDelete: (id: number) => void;
    onOpenModal: () => void;
}) {
    const providerOptions = PROVIDERS.filter((p) => p.category === category);

    return (
        <div className="mb-10">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Icon className="w-4 h-4 text-gray-400" />
                    <h2 className="text-sm font-semibold text-gray-700">
                        {title}
                    </h2>
                </div>
                <button
                    onClick={onOpenModal}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-600 hover:bg-blue-50 rounded-lg"
                >
                    <Plus className="w-3.5 h-3.5" /> Добавить
                </button>
            </div>

            {connections.length === 0 ? (
                <div className="bg-white border border-dashed border-gray-200 rounded-xl p-6 text-center">
                    <p className="text-xs text-gray-400 mb-2">
                        Пока не подключено
                    </p>
                    <div className="flex flex-wrap justify-center gap-1.5">
                        {providerOptions.map((p) => (
                            <span
                                key={p.key}
                                className={`text-[11px] px-2 py-0.5 rounded-full ${
                                    p.comingSoon
                                        ? "bg-gray-50 text-gray-300"
                                        : "bg-gray-100 text-gray-500"
                                }`}
                            >
                                {p.label}
                                {p.comingSoon ? " (скоро)" : ""}
                            </span>
                        ))}
                    </div>
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {connections.map((c) => (
                        <ConnectionCard
                            key={c.id}
                            conn={c}
                            onDelete={onDelete}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

export default function Connections() {
    const [connections, setConnections] = useState<Connection[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [modalCategory, setModalCategory] = useState<
        "ai_api" | "tool" | null
    >(null);
    const [oauthBanner, setOauthBanner] = useState<{
        ok: boolean;
        text: string;
    } | null>(null);

    useEffect(() => {
        load();
        const params = new URLSearchParams(window.location.search);
        if (params.get("connected")) {
            setOauthBanner({
                ok: true,
                text: "Google-аккаунт успешно подключён.",
            });
        } else if (params.get("error")) {
            setOauthBanner({
                ok: false,
                text: "Не получилось подключить Google — проверь настройки OAuth в .env.",
            });
        }
        if (params.get("connected") || params.get("error")) {
            window.history.replaceState({}, "", "/connections");
        }
    }, []);

    const load = async () => {
        setIsLoading(true);
        const { data } = await api.getConnections();
        if (data) setConnections(data);
        setIsLoading(false);
    };

    const handleDelete = async (id: number) => {
        if (!confirm("Удалить это подключение?")) return;
        const { error } = await api.deleteConnection(id);
        if (error) {
            alert(`Ошибка: ${error}`);
            return;
        }
        setConnections((cs) => cs.filter((c) => c.id !== id));
    };

    const aiConnections = connections.filter((c) => c.category === "ai_api");
    const toolConnections = connections.filter((c) => c.category === "tool");

    return (
        <div className="flex h-screen">
            <EditorSidebar />
            <div className="flex-1 overflow-y-auto bg-gray-50">
                <div className="max-w-3xl mx-auto px-8 py-10">
                    <h1 className="text-2xl font-bold text-gray-900">
                        Подключения
                    </h1>
                    <p className="text-sm text-gray-500 mt-1 mb-8">
                        API-ключи и токены для облачных моделей и внешних
                        сервисов
                    </p>

                    {oauthBanner && (
                        <div
                            className={`text-sm rounded-lg px-4 py-3 mb-6 border ${
                                oauthBanner.ok
                                    ? "bg-emerald-50 border-emerald-100 text-emerald-700"
                                    : "bg-red-50 border-red-100 text-red-600"
                            }`}
                        >
                            {oauthBanner.text}
                        </div>
                    )}

                    {isLoading ? (
                        <p className="text-sm text-gray-400">Загрузка...</p>
                    ) : (
                        <>
                            <CategorySection
                                title="AI API"
                                icon={Sparkles}
                                category="ai_api"
                                connections={aiConnections}
                                onDelete={handleDelete}
                                onOpenModal={() => setModalCategory("ai_api")}
                            />
                            <CategorySection
                                title="Инструменты"
                                icon={Wrench}
                                category="tool"
                                connections={toolConnections}
                                onDelete={handleDelete}
                                onOpenModal={() => setModalCategory("tool")}
                            />
                        </>
                    )}
                </div>
            </div>

            {modalCategory && (
                <ConnectionModal
                    category={modalCategory}
                    onClose={() => setModalCategory(null)}
                    onCreated={(c) => {
                        setConnections((cs) => [...cs, c]);
                        setModalCategory(null);
                    }}
                />
            )}
        </div>
    );
}
