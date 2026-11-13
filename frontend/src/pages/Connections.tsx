import { useEffect, useState } from "react";
import { Plus, Trash2, X, Sparkles, Wrench } from "lucide-react";
import { api } from "../api/client";
import type { Connection } from "../types/workflow";
import EditorSidebar from "../components/canvas/EditorSidebar";
import { EMAIL_PRESETS, PROVIDERS, TOOL_GROUPS, getProvider, type ProviderDef } from "../utils/providers";

const label = "block text-xs font-medium text-gray-500 mb-1";
const input =
    "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500";

function EmailFields({ fields, setFields, presets }: { fields: Record<string, string>; setFields: (f: Record<string, string>) => void; presets: string[] }) {
    const allowed = EMAIL_PRESETS.filter((p) => presets.includes(p.key));
    const preset = allowed.some((p) => p.key === fields.preset) ? fields.preset : allowed[0].key;
    const current = allowed.find((p) => p.key === preset) ?? allowed[0];
    const patch = (key: string, value: string) => setFields({ ...fields, preset, [key]: value });
    return (
        <>
            <div>
                {allowed.length > 1 && (
                    <>
                        <label className={label}>Почтовый сервис</label>
                        <select value={preset} onChange={(e) => setFields({ ...fields, preset: e.target.value })} className={input}>
                            {allowed.map((p) => (
                                <option key={p.key} value={p.key}>
                                    {p.label}
                                </option>
                            ))}
                        </select>
                    </>
                )}
                <p className="mt-1 text-xs leading-snug text-gray-500">{current.help}</p>
            </div>
            <div>
                <label className={label}>Адрес электронной почты</label>
                <input value={fields.email || ""} onChange={(e) => patch("email", e.target.value)} placeholder="info@yourcompany.ru" className={input} />
            </div>
            <div>
                <label className={label}>Пароль приложения</label>
                <input type="password" value={fields.password || ""} onChange={(e) => patch("password", e.target.value)} className={input} />
            </div>
            {preset === "custom" && (
                <div className="grid grid-cols-2 gap-2">
                    <input value={fields.imap_host || ""} onChange={(e) => patch("imap_host", e.target.value)} placeholder="Сервер IMAP: imap.example.com" className={input} />
                    <input value={fields.imap_port || ""} onChange={(e) => patch("imap_port", e.target.value)} placeholder="Порт IMAP: 993" className={input} />
                    <input value={fields.smtp_host || ""} onChange={(e) => patch("smtp_host", e.target.value)} placeholder="Сервер SMTP: smtp.example.com" className={input} />
                    <input value={fields.smtp_port || ""} onChange={(e) => patch("smtp_port", e.target.value)} placeholder="Порт SMTP: 465" className={input} />
                </div>
            )}
        </>
    );
}

function ConnectionModal({
    category,
    onClose,
    onCreated,
    oauthStatus,
}: {
    category: "ai_api" | "tool";
    onClose: () => void;
    onCreated: (c: Connection) => void;
    oauthStatus: Record<string, boolean>;
}) {
    const isTool = category === "tool";
    const options = PROVIDERS.filter((p) => p.category === category);
    const [providerKeyState, setProviderKey] = useState(options[0]?.key || "");
    const [groupKey, setGroupKey] = useState(TOOL_GROUPS[0].key);
    const [serviceIdx, setServiceIdx] = useState(0);
    const [methodIdx, setMethodIdx] = useState(0);
    const group = TOOL_GROUPS.find((g) => g.key === groupKey) ?? TOOL_GROUPS[0];
    const service = group.services[Math.min(serviceIdx, group.services.length - 1)];
    const method = service.methods[Math.min(methodIdx, service.methods.length - 1)];
    const providerKey = isTool ? method.providerKey : providerKeyState;
    const [name, setName] = useState("");
    const [fields, setFields] = useState<Record<string, string>>({});
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const provider = getProvider(providerKey) as ProviderDef;
    const notConfigured = !!provider?.oauth && !!provider.family && oauthStatus[provider.family] === false;

    const handleSubmit = async () => {
        if (!name.trim()) {
            setError("Укажите название подключения");
            return;
        }
        setSaving(true);
        setError(null);

        if (provider?.oauth) {
            const { data, error } = await api.startOAuth(
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
            config: provider?.emailForm ? { ...fields, preset: fields.preset && (method.presets || []).includes(fields.preset) ? fields.preset : (method.presets || ["gmail"])[0] } : fields,
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
                    {isTool ? (
                        <>
                            <div>
                                <label className={label}>Что подключить</label>
                                <select
                                    value={groupKey}
                                    onChange={(e) => {
                                        setGroupKey(e.target.value);
                                        setServiceIdx(0);
                                        setMethodIdx(0);
                                        setFields({});
                                    }}
                                    className={input}
                                >
                                    {TOOL_GROUPS.map((g) => (
                                        <option key={g.key} value={g.key}>
                                            {g.label}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            {group.services.length > 1 && (
                                <div>
                                    <label className={label}>Сервис</label>
                                    <select
                                        value={serviceIdx}
                                        onChange={(e) => {
                                            setServiceIdx(Number(e.target.value));
                                            setMethodIdx(0);
                                            setFields({});
                                        }}
                                        className={input}
                                    >
                                        {group.services.map((svc, i) => (
                                            <option key={svc.label} value={i}>
                                                {svc.label}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                            )}
                            {service.methods.length > 1 && (
                                <div>
                                    <label className={label}>Способ входа</label>
                                    <div className="space-y-1.5">
                                        {service.methods.map((m, i) => (
                                            <label key={m.label} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                                                <input
                                                    type="radio"
                                                    name="connect-method"
                                                    checked={i === methodIdx}
                                                    onChange={() => {
                                                        setMethodIdx(i);
                                                        setFields({});
                                                    }}
                                                />
                                                {m.label}
                                            </label>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </>
                    ) : (
                        <div>
                            <label className={label}>Сервис</label>
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
                    )}

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
                        <>
                            <p className="text-xs text-blue-600 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
                                Откроется страница входа {provider.service}. После Вашего согласия подключение появится здесь автоматически.
                                {provider.note ? ` ${provider.note}.` : ""}
                            </p>
                            {notConfigured && (
                                <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                                    Вход через {provider.service} на этом сервере ещё не настроен: администратору нужно создать приложение в кабинете
                                    разработчика и указать ключи в файле <code>.env</code>.
                                </p>
                            )}
                        </>
                    ) : provider?.emailForm ? (
                        <EmailFields fields={fields} setFields={setFields} presets={method.presets || ["gmail"]} />
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

                    {provider?.guide && (
                        <p className="text-xs leading-snug text-gray-500 bg-gray-50 border border-gray-100 rounded-lg px-3 py-2">{provider.guide}</p>
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
                        disabled={saving || provider?.comingSoon || notConfigured}
                        className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                    >
                        {saving
                            ? "..."
                            : provider?.oauth
                              ? `Войти через ${provider.service}`
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
    onReconnect,
}: {
    conn: Connection;
    onDelete: (id: number) => void;
    onReconnect: (conn: Connection) => void;
}) {
    const provider = getProvider(conn.provider);
    // Технические поля и токены в карточке не показываем: для OAuth важны только аккаунт и статус
    const details = conn.oauth ? [] : Object.entries(conn.config).filter(([k]) => k !== "account");
    return (
        <div className={`bg-white border rounded-xl p-4 flex items-start justify-between gap-2 ${conn.needs_reauth ? "border-amber-300" : "border-gray-200"}`}>
            <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-900 truncate">{conn.name}</p>
                <p className="text-xs text-gray-400 mt-0.5">{provider?.label || conn.provider}</p>
                {conn.account && <p className="text-xs text-gray-600 mt-1 truncate">Аккаунт: {conn.account}</p>}
                {conn.needs_reauth && (
                    <div className="mt-2 rounded-lg bg-amber-50 border border-amber-200 px-2.5 py-1.5">
                        <p className="text-xs text-amber-800">Доступ истёк или отозван. Шаги с этим подключением не работают.</p>
                        <button onClick={() => onReconnect(conn)} className="mt-1 text-xs font-medium text-blue-600 hover:underline">
                            Войти заново
                        </button>
                    </div>
                )}
                {details.length > 0 && (
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-2">
                        {details.map(([k, v]) => (
                            <span key={k} className="text-[11px] font-mono text-gray-400">
                                {k}: {String(v)}
                            </span>
                        ))}
                    </div>
                )}
                {provider?.usedFor && <p className="text-[11px] text-indigo-500 mt-2">Используется для: {provider.usedFor}</p>}
            </div>
            <button
                onClick={() => onDelete(conn.id)}
                title="Удалить подключение (доступ в сервисе будет отозван, где это возможно)"
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
    onReconnect,
}: {
    title: string;
    icon: typeof Sparkles;
    category: "ai_api" | "tool";
    connections: Connection[];
    onDelete: (id: number) => void;
    onOpenModal: () => void;
    onReconnect: (conn: Connection) => void;
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
                            onReconnect={onReconnect}
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
    const [oauthStatus, setOauthStatus] = useState<Record<string, boolean>>({});

    useEffect(() => {
        load();
        api.getOAuthStatus().then(({ data }) => data && setOauthStatus(data));
        const params = new URLSearchParams(window.location.search);
        const providerName = getProvider(params.get("provider") || "")?.label || "сервис";
        const reasons: Record<string, string> = {
            oauth_denied: `Вы отказались дать доступ: подключение «${providerName}» не создано.`,
            missing_scope: `Не выдано нужное право доступа. Войдите снова и оставьте все галочки на экране согласия («${providerName}»).`,
            no_email: "Не удалось определить адрес почты аккаунта. Войдите снова и разрешите доступ к адресу почты.",
            too_many_connections: "Достигнут лимит подключений. Удалите ненужные и повторите.",
            oauth_failed: `Не получилось подключить «${providerName}». Попробуйте ещё раз; если повторяется — сообщите администратору.`,
        };
        if (params.get("connected")) {
            setOauthBanner({ ok: true, text: `Подключено: ${providerName}.` });
        } else if (params.get("error")) {
            setOauthBanner({ ok: false, text: reasons[params.get("error") || ""] || reasons.oauth_failed });
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

    const handleReconnect = async (conn: Connection) => {
        const { data, error } = await api.startOAuth(conn.provider, conn.name, conn.id);
        if (error) {
            alert(`Ошибка: ${error}`);
            return;
        }
        if (data?.auth_url) window.location.href = data.auth_url;
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
                        Доступ к Вашим аккаунтам: нейросети, Telegram, почта, Google. Где возможно, вход идёт через аккаунт сервиса, без передачи пароля
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
                                onReconnect={handleReconnect}
                            />
                            <CategorySection
                                title="Инструменты"
                                icon={Wrench}
                                category="tool"
                                connections={toolConnections}
                                onDelete={handleDelete}
                                onOpenModal={() => setModalCategory("tool")}
                                onReconnect={handleReconnect}
                            />
                        </>
                    )}
                </div>
            </div>

            {modalCategory && (
                <ConnectionModal
                    category={modalCategory}
                    onClose={() => setModalCategory(null)}
                    oauthStatus={oauthStatus}
                    onCreated={(c) => {
                        setConnections((cs) => [...cs, c]);
                        setModalCategory(null);
                    }}
                />
            )}
        </div>
    );
}
