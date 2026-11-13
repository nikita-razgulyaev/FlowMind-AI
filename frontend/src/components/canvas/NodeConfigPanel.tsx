import { useEffect, useState } from "react";
import { X, Trash2 } from "lucide-react";
import type { WorkflowNode, Connection } from "../../types/workflow";
import { api } from "../../api/client";
import { NODE_META } from "./CanvasNode";
import { useAuth } from "../../store/auth";
import ToolSettingsFields, { TOOL_PRESETS } from "./ToolSettings";
import { NODE_INFO } from "../../utils/glossary";
import { OPERATIONS, TEXT_OPERATIONS } from "../../utils/textOperations";

const LLM_MODELS = {
    local: [
        { value: "qwen2.5", label: "Qwen 2.5 (Ollama)" },
        { value: "llama3.1", label: "Llama 3.1 (Ollama)" },
        { value: "mistral", label: "Mistral (Ollama)" },
    ],
};

const label = "block text-xs font-medium text-gray-500 mb-1";
const mono = "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500";
const input =
    "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500";

interface Props {
    node: WorkflowNode;
    workflowId?: number;
    onChange: (config: Record<string, any>) => void;
    onDelete: () => void;
    onClose: () => void;
}

interface PlatformModel {
    name: string;
    model: string;
    main: boolean;
}

/** Выбор модели: для встроенного AI — модели из секретов сервера (основная выбрана по умолчанию), для своего подключения — модели из него. */
function ModelPicker({
    cfg,
    set,
    aiConnections,
    platformModels,
}: {
    cfg: Record<string, any>;
    set: (patch: Record<string, any>) => void;
    aiConnections: Connection[];
    platformModels: PlatformModel[];
}) {
    const isLocal = cfg.mode === "local";
    const conn = isLocal ? undefined : aiConnections.find((c) => c.id === cfg.connection_id);
    const own = String(conn?.config?.models || "")
        .split(",")
        .map((m) => m.trim())
        .filter(Boolean);
    const main = platformModels.find((m) => m.main);

    let options: { value: string; label: string }[];
    let emptyHint: string | null = null;
    if (isLocal) {
        options = LLM_MODELS.local;
    } else if (conn) {
        if (own.length === 0) {
            options = [{ value: "", label: "Нет моделей" }];
            emptyHint = "В подключении не указаны модели. Добавьте их в разделе «Подключения».";
        } else {
            options = [{ value: "", label: "По умолчанию подключения" }, ...own.map((m) => ({ value: m, label: m }))];
        }
    } else if (platformModels.length === 0) {
        options = [{ value: "", label: "Нет моделей" }];
        emptyHint = "Встроенные модели не настроены на сервере (PLATFORM_LLM_PROVIDERS / ключи в .env).";
    } else {
        options = [
            { value: "", label: main ? `По умолчанию: ${main.model}` : "По умолчанию (модель сервиса)" },
            ...platformModels.map((m) => ({ value: m.model, label: `${m.model} — ${m.main ? "основная" : "запасная"}` })),
        ];
    }

    // Только встроенные модели (из .env / platform) и модели из подключений пользователя — без ручного ввода
    return (
        <div>
            <label className={label}>Модель</label>
            <select
                value={cfg.model ?? ""}
                onChange={(e) => set({ model: e.target.value })}
                className={input}
                disabled={!!emptyHint}
            >
                {options.map((o) => (
                    <option key={o.value || "default"} value={o.value}>
                        {o.label}
                    </option>
                ))}
            </select>
            {emptyHint && <p className="text-xs text-amber-600 mt-1">{emptyHint}</p>}
            {!isLocal && !conn && platformModels.length > 1 && (
                <p className="text-xs text-gray-400 mt-1">Если выбранная модель не ответит, сервис автоматически переключится на другую.</p>
            )}
        </div>
    );
}

function ConnectHint({ what }: { what: string }) {
    return (
        <p className="text-xs text-amber-600 mt-1">
            Нет подключений: {what}.{" "}
            <a href="/connections" target="_blank" rel="noreferrer" className="underline hover:text-amber-700">
                Добавить подключение
            </a>{" "}
            (откроется в новой вкладке), затем вернитесь и выберите его в списке.
        </p>
    );
}

function TestInputField({
    cfg,
    set,
    hint,
}: {
    cfg: Record<string, any>;
    set: (patch: Record<string, any>) => void;
    hint?: string;
}) {
    return (
        <div>
            <label className={label}>Тестовое сообщение для кнопки «Запустить» (подставится в {"{input}"})</label>
            <textarea
                value={cfg.test_input || ""}
                onChange={(e) => set({ test_input: e.target.value })}
                rows={4}
                placeholder={hint || "Текст, который подставится вместо сообщения клиента при проверке"}
                className={input}
            />
        </div>
    );
}

const TEXT_FILE_ACCEPT =
    ".txt,.md,.markdown,.csv,.tsv,.json,.jsonl,.log,.xml,.html,.htm,.yaml,.yml,.ini,.toml,.srt,.vtt,.rtf,.tex,text/*";
const MAX_TEXT_FILE_BYTES = 500_000;

function TextInputFields({
    cfg,
    set,
}: {
    cfg: Record<string, any>;
    set: (patch: Record<string, any>) => void;
}) {
    const [error, setError] = useState("");

    const handleFile = async (file?: File) => {
        if (!file) return;
        if (file.size > MAX_TEXT_FILE_BYTES) {
            setError("Файл больше 500 КБ");
            return;
        }
        setError("");
        set({ text: await file.text(), file_name: file.name });
    };

    return (
        <>
            <div>
                <label className={label}>Текст (в других шагах доступен как {"{имя_шага}"})</label>
                <textarea
                    value={cfg.text || ""}
                    onChange={(e) => set({ text: e.target.value, file_name: "" })}
                    rows={8}
                    placeholder="Вставьте текст..."
                    className={input}
                />
                <p className="text-xs text-gray-400 mt-1">
                    {(cfg.text || "").length} символов
                    {cfg.file_name ? ` · из файла ${cfg.file_name}` : ""}
                </p>
            </div>
            <div>
                <label className={label}>Или загрузите текстовый файл</label>
                <input
                    type="file"
                    accept={TEXT_FILE_ACCEPT}
                    onChange={(e) => {
                        handleFile(e.target.files?.[0]);
                        e.target.value = "";
                    }}
                    className="block w-full text-xs text-gray-500 file:mr-3 file:rounded-lg file:border-0 file:bg-blue-50 file:px-3 file:py-2 file:text-xs file:font-medium file:text-blue-700 hover:file:bg-blue-100"
                />
                <p className="text-xs text-gray-400 mt-1">
                    txt, md, csv, json, log, xml, html, yaml, srt и другие текстовые форматы, до 500 КБ. Файл заменяет текст выше.
                </p>
                {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
            </div>
        </>
    );
}

function WebhookUrl({ workflowId }: { workflowId?: number }) {
    const [url, setUrl] = useState("");
    useEffect(() => {
        if (!workflowId) return;
        api.getWebhookUrl(workflowId).then(({ data }) => data && setUrl(data.url));
    }, [workflowId]);
    if (!workflowId) {
        return <p className="text-xs text-amber-600">Сохраните сценарий — появится ссылка для вызова (webhook).</p>;
    }
    return (
        <div>
            <label className={label}>Ссылка для вызова (GET или POST). Сценарий должен быть включён</label>
            <input readOnly value={url} onFocus={(e) => e.target.select()} className={input} />
            <p className="text-xs text-gray-400 mt-1">
                Тело запроса: {"{input}"} — текст, {"{webhook.body.поле}"} — поле JSON, {"{webhook.query.параметр}"} — query-параметр.
            </p>
        </div>
    );
}

export default function NodeConfigPanel({
    node,
    workflowId,
    onChange,
    onDelete,
    onClose,
}: Props) {
    const meta = NODE_META[node.type] ?? NODE_META.print;
    const cfg = node.config || {};
    const set = (patch: Record<string, any>) => onChange({ ...cfg, ...patch });

    const [connections, setConnections] = useState<Connection[]>([]);
    // В облачной версии локальные модели (Ollama) недоступны — режим только Cloud.
    const isCloudDeployment = useAuth((st) => st.config?.deployment_mode === "cloud");
    const modes = (isCloudDeployment ? ["cloud"] : ["local", "cloud"]) as ("local" | "cloud")[];

    useEffect(() => {
        api.getConnections().then(({ data }) => {
            if (data) setConnections(data);
        });
    }, []);

    const aiConnections = connections.filter((c) => c.category === "ai_api");
    const [platformModels, setPlatformModels] = useState<PlatformModel[]>([]);
    useEffect(() => {
        api.getAiModels().then(({ data }) => data && setPlatformModels(data.models));
    }, []);
    const openaiConnections = aiConnections.filter(
        (c) => c.provider === "openai_compatible" || c.provider === "huggingface",
    );
    const telegramConnections = connections.filter(
        (c) => c.category === "tool" && c.provider === "telegram_bot",
    );
    const sheetsConnections = connections.filter(
        (c) => c.category === "tool" && (c.provider === "google_sheets" || c.provider === "yandex_sheets"),
    );
    const MAIL_PROVIDERS = ["email", "google_gmail", "yandex_mail", "mailru_mail"];
    const emailConnections = connections.filter((c) => c.category === "tool" && MAIL_PROVIDERS.includes(c.provider));
    const calendarConnections = connections.filter(
        (c) => c.category === "tool" && (c.provider === "google_calendar" || c.provider === "yandex_calendar"),
    );
    const selectedCalendar = calendarConnections.find((c) => c.id === cfg.connection_id);
    const isYandexCalendar = selectedCalendar?.provider === "yandex_calendar";

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

            {NODE_INFO[node.type] && (
                <p className="px-4 pt-3 text-xs leading-snug text-gray-500">{NODE_INFO[node.type].hint}</p>
            )}

            <div className="p-4 space-y-4">
                {node.type === "llm" && (
                    <>
                        <div className="flex gap-2">
                            {modes.map((m) => (
                                <button
                                    key={m}
                                    onClick={() =>
                                        set({
                                            mode: m,
                                            model: m === "local" ? LLM_MODELS.local[0].value : "",
                                        })
                                    }
                                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium ${
                                        cfg.mode === m
                                            ? "bg-blue-600 text-white"
                                            : "bg-gray-100 text-gray-600"
                                    }`}
                                >
                                    {m === "local" ? "Local (Ollama)" : "Cloud"}
                                </button>
                            ))}
                        </div>

                        {cfg.mode === "cloud" && (
                            <div>
                                <label className={label}>
                                    Подключение нейросети (раздел «Подключения»)
                                </label>
                                <select
                                    value={cfg.connection_id ?? ""}
                                    onChange={(e) =>
                                        set({
                                            connection_id: e.target.value
                                                ? Number(e.target.value)
                                                : undefined,
                                        })
                                    }
                                    className={input}
                                >
                                    <option value="">
                                        — AI сервиса (по лимитам тарифа) —
                                    </option>
                                    {aiConnections.map((c) => (
                                        <option key={c.id} value={c.id}>
                                            {c.name} ({c.provider})
                                        </option>
                                    ))}
                                </select>
                            </div>
                        )}

                        <ModelPicker cfg={cfg} set={set} aiConnections={aiConnections} platformModels={platformModels} />
                        <div>
                            <label className={label}>
                                Запрос к нейросети (промпт). В нём можно использовать {"{input}"} — сообщение клиента — и {"{имя_шага}"} — результат другого шага
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
                        <div>
                            <label className={label}>Headers (JSON, необязательно)</label>
                            <input
                                value={cfg.headers || ""}
                                onChange={(e) => set({ headers: e.target.value })}
                                placeholder='{"Authorization": "Bearer ..."}'
                                className={input}
                            />
                        </div>
                        {cfg.method === "POST" && (
                            <div>
                                <label className={label}>Body (JSON или текст)</label>
                                <textarea
                                    value={cfg.body || ""}
                                    onChange={(e) => set({ body: e.target.value })}
                                    rows={3}
                                    className={input}
                                />
                            </div>
                        )}
                        <p className="text-xs text-gray-400">
                            Если сервис ответил данными в формате JSON, их можно использовать так: {"{имя_шага.json.поле}"}.
                        </p>
                        <ToolSettingsFields key={node.id} cfg={cfg} set={set} preset={TOOL_PRESETS.http} />
                    </>
                )}

                {node.type === "telegram_send" && (
                    <>
                        <div>
                            <label className={label}>
                                Подключение: Telegram-бот
                            </label>
                            <select
                                value={cfg.connection_id ?? ""}
                                onChange={(e) =>
                                    set({
                                        connection_id: e.target.value
                                            ? Number(e.target.value)
                                            : undefined,
                                    })
                                }
                                className={input}
                            >
                                <option value="">— выберите подключение —</option>
                                {telegramConnections.map((c) => (
                                    <option key={c.id} value={c.id}>
                                        {c.name}
                                    </option>
                                ))}
                            </select>
                            {telegramConnections.length === 0 && (
                                <ConnectHint what="Telegram Bot" />
                            )}
                        </div>
                        <div>
                            <label className={label}>
                                Куда отправить: ID чата или канал (оставьте пустым — ответ уйдёт тому, кто написал)
                            </label>
                            <input
                                value={cfg.chat_id || ""}
                                onChange={(e) =>
                                    set({ chat_id: e.target.value })
                                }
                                placeholder="123456789 или @имя_канала"
                                className={input}
                            />
                            <p className="text-xs text-gray-400 mt-1">
                                Для канала укажите @имя или ссылку t.me/имя и добавьте бота администратором с правом публикации.
                            </p>
                        </div>
                        <div>
                            <label className={label}>Картинка: прямая ссылка (необязательно)</label>
                            <input
                                value={cfg.photo_url || ""}
                                onChange={(e) => set({ photo_url: e.target.value })}
                                placeholder="https://example.com/cover.jpg"
                                className={input}
                            />
                            <p className="text-xs text-gray-400 mt-1">С картинкой текст становится подписью (до 1024 знаков), более длинный уходит отдельным сообщением.</p>
                        </div>
                        <div>
                            <label className={label}>
                                Сообщение (результаты других шагов подставляются в фигурных скобках, например {"{reply}"})
                            </label>
                            <textarea
                                value={cfg.message || ""}
                                onChange={(e) =>
                                    set({ message: e.target.value })
                                }
                                rows={3}
                                placeholder="Здравствуйте, {input}!"
                                className={input}
                            />
                        </div>
                        <ToolSettingsFields key={node.id} cfg={cfg} set={set} preset={TOOL_PRESETS.telegram_send} />
                    </>
                )}

                {node.type === "google_sheets_append" && (
                    <>
                        <div>
                            <label className={label}>
                                Подключение: таблицы
                            </label>
                            <select
                                value={cfg.connection_id ?? ""}
                                onChange={(e) =>
                                    set({
                                        connection_id: e.target.value
                                            ? Number(e.target.value)
                                            : undefined,
                                    })
                                }
                                className={input}
                            >
                                <option value="">— выберите подключение —</option>
                                {sheetsConnections.map((c) => (
                                    <option key={c.id} value={c.id}>
                                        {c.name}
                                        {c.provider === "yandex_sheets" ? " (Яндекс)" : " (Google)"}
                                    </option>
                                ))}
                            </select>
                            {sheetsConnections.length === 0 && (
                                <ConnectHint what="Google или Яндекс Таблицы" />
                            )}
                        </div>
                        {sheetsConnections.find((c) => c.id === cfg.connection_id)?.provider === "yandex_sheets" ? (
                            <div>
                                <label className={label}>
                                    Путь к файлу на Яндекс Диске (CSV)
                                </label>
                                <input
                                    value={cfg.spreadsheet_id || ""}
                                    onChange={(e) =>
                                        set({ spreadsheet_id: e.target.value })
                                    }
                                    placeholder="disk:/Таблицы/заявки.csv"
                                    className={input}
                                />
                                <p className="text-[11px] text-gray-400 mt-1">
                                    Полный путь к CSV-файлу на Диске. Строка будет добавлена в конец файла.
                                </p>
                            </div>
                        ) : (
                            <div>
                                <label className={label}>
                                    ID таблицы (часть адреса между /d/ и /edit)
                                </label>
                                <input
                                    value={cfg.spreadsheet_id || ""}
                                    onChange={(e) =>
                                        set({ spreadsheet_id: e.target.value })
                                    }
                                    placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
                                    className={input}
                                />
                                <p className="text-[11px] text-gray-400 mt-1">
                                    Часть URL таблицы между /d/ и /edit
                                </p>
                            </div>
                        )}
                        <div>
                            <label className={label}>
                                Лист и ячейка, с которой начать поиск места для записи
                            </label>
                            <input
                                value={cfg.range || "A1"}
                                onChange={(e) => set({ range: e.target.value })}
                                placeholder="Sheet1!A1"
                                className={input}
                            />
                        </div>
                        <div>
                            <label className={label}>
                                Значения строки через запятую (можно подставлять данные в фигурных скобках)
                            </label>
                            <input
                                value={cfg.values || ""}
                                onChange={(e) =>
                                    set({ values: e.target.value })
                                }
                                placeholder="{client_name}, {phone}, {order_id}"
                                className={input}
                            />
                        </div>
                        <ToolSettingsFields key={node.id} cfg={cfg} set={set} preset={TOOL_PRESETS.google_sheets_append} />
                    </>
                )}

                {node.type === "google_calendar_create_event" && (
                    <>
                        <div>
                            <label className={label}>
                                Подключение: календарь (Google или Яндекс)
                            </label>
                            <select
                                value={cfg.connection_id ?? ""}
                                onChange={(e) =>
                                    set({
                                        connection_id: e.target.value
                                            ? Number(e.target.value)
                                            : undefined,
                                    })
                                }
                                className={input}
                            >
                                <option value="">— выберите подключение —</option>
                                {calendarConnections.map((c) => (
                                    <option key={c.id} value={c.id}>
                                        {c.name}{c.account ? ` (${c.account})` : ""}{c.needs_reauth ? " — нужен повторный вход" : ""}
                                    </option>
                                ))}
                            </select>
                            {calendarConnections.length === 0 && (
                                <ConnectHint what="Google Календарь или Яндекс Календарь" />
                            )}
                        </div>
                        <div>
                            <label className={label}>
                                {isYandexCalendar ? "Название календаря (пусто — основной)" : "ID календаря Google (primary — основной)"}
                            </label>
                            <input
                                value={isYandexCalendar ? (cfg.calendar_id === "primary" ? "" : cfg.calendar_id ?? "") : cfg.calendar_id || "primary"}
                                onChange={(e) =>
                                    set({ calendar_id: e.target.value })
                                }
                                placeholder={isYandexCalendar ? "Например: Работа" : "primary"}
                                className={input}
                            />
                        </div>
                        <div>
                            <label className={label}>
                                Название события (данные из других шагов подставляются в фигурных скобках)
                            </label>
                            <input
                                value={cfg.summary || ""}
                                onChange={(e) =>
                                    set({ summary: e.target.value })
                                }
                                placeholder="Встреча с {client_name}"
                                className={input}
                            />
                        </div>
                        <div>
                            <label className={label}>Описание</label>
                            <input
                                value={cfg.description || ""}
                                onChange={(e) =>
                                    set({ description: e.target.value })
                                }
                                className={input}
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                            <div>
                                <label className={label}>
                                    Начало (например, 2026-08-01T15:00:00+03:00)
                                </label>
                                <input
                                    value={cfg.start_datetime || ""}
                                    onChange={(e) =>
                                        set({ start_datetime: e.target.value })
                                    }
                                    placeholder="2026-08-01T15:00:00+03:00"
                                    className={input}
                                />
                            </div>
                            <div>
                                <label className={label}>
                                    Конец (например, 2026-08-01T16:00:00+03:00)
                                </label>
                                <input
                                    value={cfg.end_datetime || ""}
                                    onChange={(e) =>
                                        set({ end_datetime: e.target.value })
                                    }
                                    placeholder="2026-08-01T16:00:00+03:00"
                                    className={input}
                                />
                            </div>
                        </div>
                        <ToolSettingsFields key={node.id} cfg={cfg} set={set} preset={TOOL_PRESETS.google_calendar_create_event} />
                    </>
                )}

                {node.type === "condition" && (
                    <div>
                        <label className={label}>
                            Условие (например, оценка не ниже 7)
                        </label>
                        <input
                            value={cfg.expression || ""}
                            onChange={(e) =>
                                set({ expression: e.target.value })
                            }
                            placeholder="{extract.score} >= 7"
                            className={input}
                        />
                        <p className="text-xs text-gray-400 mt-1">
                            Выполнится только выбранная ветка: проведите связь от
                            ветки «true» (условие выполнено) или «false» (не выполнено). Данные из ответа другого шага берутся так:{" "}
                            {"{имя_шага.поле}"}.
                        </p>
                    </div>
                )}

                {node.type === "switch" && (
                    <>
                        <div>
                            <label className={label}>Значение</label>
                            <input
                                value={cfg.value || ""}
                                onChange={(e) => set({ value: e.target.value })}
                                placeholder="{classify}"
                                className={input}
                            />
                        </div>
                        <div>
                            <label className={label}>Варианты (через запятую)</label>
                            <input
                                value={cfg.cases || ""}
                                onChange={(e) => set({ cases: e.target.value })}
                                placeholder="support, sales, complaint"
                                className={input}
                            />
                            <p className="text-xs text-gray-400 mt-1">
                                Сравнение без регистра и знаков препинания (допускается вхождение). Если ни один вариант не подошёл — сработает ветка «default».
                            </p>
                        </div>
                    </>
                )}

                {node.type === "set" && (
                    <div>
                        <label className={label}>Значения (key=value, по строке)</label>
                        <textarea
                            value={cfg.values || ""}
                            onChange={(e) => set({ values: e.target.value })}
                            rows={5}
                            placeholder={"name={extract.name}\nsource=telegram"}
                            className={input}
                        />
                        <p className="text-xs text-gray-400 mt-1">
                            Дальше доступны как {"{имя_шага.имя}"}.
                        </p>
                    </div>
                )}

                {node.type === "print" && (
                    <div>
                        <label className={label}>
                            Что показать (результат другого шага указывается в фигурных скобках, например {"{reply}"})
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
                            {modes.map((m) => (
                                <button
                                    key={m}
                                    onClick={() => set({ mode: m })}
                                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium ${
                                        (cfg.mode || "local") === m
                                            ? "bg-indigo-600 text-white"
                                            : "bg-gray-100 text-gray-600"
                                    }`}
                                >
                                    {m === "local" ? "Local (Ollama)" : "Cloud"}
                                </button>
                            ))}
                        </div>

                        {cfg.mode === "cloud" && (
                            <div>
                                <label className={label}>
                                    Подключение (нужна модель с tool calling;
                                    без подключения — AI сервиса)
                                </label>
                                <select
                                    value={cfg.connection_id ?? ""}
                                    onChange={(e) =>
                                        set({
                                            connection_id: e.target.value
                                                ? Number(e.target.value)
                                                : undefined,
                                        })
                                    }
                                    className={input}
                                >
                                    <option value="">
                                        — AI сервиса (по лимитам тарифа) —
                                    </option>
                                    {openaiConnections.map((c) => (
                                        <option key={c.id} value={c.id}>
                                            {c.name}
                                        </option>
                                    ))}
                                </select>
                                {openaiConnections.length === 0 && (
                                    <p className="text-xs text-gray-400 mt-1">
                                        Свои ключи (OpenAI-совместимые, Hugging Face)
                                        добавляются на странице «Подключения».
                                    </p>
                                )}
                            </div>
                        )}

                        <ModelPicker cfg={cfg} set={set} aiConnections={aiConnections} platformModels={platformModels} />
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
                            Инструменты подключаются связью от нижнего разъёма агента («↓ инструменты агента») к любому шагу на рабочей области: запросу к сервису, Telegram, таблице, календарю или почте.
                        </p>
                    </>
                )}

                {node.type === "telegram_trigger" && (
                    <>
                        <div>
                            <label className={label}>
                                Telegram-бот (раздел «Подключения»)
                            </label>
                            <select
                                value={cfg.connection_id ?? ""}
                                onChange={(e) =>
                                    set({
                                        connection_id: e.target.value
                                            ? Number(e.target.value)
                                            : undefined,
                                    })
                                }
                                className={input}
                            >
                                <option value="">— выберите подключение —</option>
                                {telegramConnections.map((c) => (
                                    <option key={c.id} value={c.id}>
                                        {c.name}
                                    </option>
                                ))}
                            </select>
                            {telegramConnections.length === 0 && (
                                <ConnectHint what="Telegram Bot" />
                            )}
                        </div>
                        <div>
                            <label className={label}>
                                Разрешённые ID чатов (через запятую; пусто — отвечать всем)
                            </label>
                            <input
                                value={cfg.allowed_chat_ids || ""}
                                onChange={(e) =>
                                    set({ allowed_chat_ids: e.target.value })
                                }
                                placeholder="123456789, 987654321"
                                className={input}
                            />
                            <p className="text-xs text-gray-400 mt-1">
                                Пусто — бот принимает сообщения от всех пользователей, написанные после включения сценария.
                            </p>
                        </div>
                        <label className="flex items-center gap-2 text-sm text-gray-600">
                            <input
                                type="checkbox"
                                checked={!!cfg.only_commands}
                                onChange={(e) =>
                                    set({ only_commands: e.target.checked })
                                }
                            />
                            Реагировать только на команды (/start, /help…)
                        </label>
                        <p className="text-xs text-gray-400">
                            Сценарий запускается на каждое входящее сообщение боту,
                            пока сценарий включён (кнопка «Включить» вверху
                            экрана). Доступны переменные {"{input}"},{" "}
                            {"{telegram_chat_id}"}, {"{telegram_username}"},{" "}
                            {"{telegram_first_name}"}. Шаг «Ответ в Telegram» с пустым
                            ID чата отвечает в тот же чат.
                        </p>
                        <TestInputField
                            cfg={cfg}
                            set={set}
                            hint="Тестовое сообщение клиента"
                        />
                        <div>
                            <label className={label}>
                                Тестовый chat_id (куда отвечать при Run)
                            </label>
                            <input
                                value={cfg.test_chat_id || ""}
                                onChange={(e) => set({ test_chat_id: e.target.value })}
                                placeholder="ваш chat_id"
                                className={input}
                            />
                        </div>
                    </>
                )}

                {node.type === "manual" && <TestInputField cfg={cfg} set={set} />}

                {node.type === "text_input" && <TextInputFields cfg={cfg} set={set} />}

                {node.type === "webhook" && (
                    <>
                        <WebhookUrl workflowId={workflowId} />
                        <TestInputField cfg={cfg} set={set} hint='{"email": "a@b.ru"}' />
                    </>
                )}



                {node.type === "email_trigger" && (
                    <>
                        <div>
                            <label className={label}>Подключённая почта</label>
                            <select
                                value={cfg.connection_id ?? ""}
                                onChange={(e) => set({ connection_id: e.target.value ? Number(e.target.value) : undefined })}
                                className={input}
                            >
                                <option value="">— выберите подключение —</option>
                                {emailConnections.map((c) => (
                                    <option key={c.id} value={c.id}>
                                        {c.name}{c.account ? ` (${c.account})` : ""}{c.needs_reauth ? " — нужен повторный вход" : ""}
                                    </option>
                                ))}
                            </select>
                            {emailConnections.length === 0 && <ConnectHint what="почта" />}
                        </div>
                        <div>
                            <label className={label}>Как часто проверять почту, минут</label>
                            <input
                                type="number"
                                min={1}
                                value={cfg.interval_minutes ?? 5}
                                onChange={(e) => set({ interval_minutes: Number(e.target.value) || 5 })}
                                className={input}
                            />
                            <p className="text-xs text-gray-400 mt-1">
                                Обрабатываются только письма, пришедшие после включения сценария. Письма остаются непрочитанными. В облаке минимум 5 минут.
                                Текст письма доступен в других шагах как {"{input}"}, адрес отправителя — {"{email_from}"}, тема — {"{email_subject}"}.
                            </p>
                        </div>
                        <div>
                            <label className={label}>Для проверки: адрес отправителя</label>
                            <input value={cfg.test_from || ""} onChange={(e) => set({ test_from: e.target.value })} placeholder="client@example.com" className={input} />
                        </div>
                        <div>
                            <label className={label}>Для проверки: тема письма</label>
                            <input value={cfg.test_subject || ""} onChange={(e) => set({ test_subject: e.target.value })} placeholder="Вопрос по заказу" className={input} />
                        </div>
                        <TestInputField cfg={cfg} set={set} />
                    </>
                )}

                {node.type === "email_send" && (
                    <>
                        <div>
                            <label className={label}>Подключённая почта</label>
                            <select
                                value={cfg.connection_id ?? ""}
                                onChange={(e) => set({ connection_id: e.target.value ? Number(e.target.value) : undefined })}
                                className={input}
                            >
                                <option value="">— выберите подключение —</option>
                                {emailConnections.map((c) => (
                                    <option key={c.id} value={c.id}>
                                        {c.name}{c.account ? ` (${c.account})` : ""}{c.needs_reauth ? " — нужен повторный вход" : ""}
                                    </option>
                                ))}
                            </select>
                            {emailConnections.length === 0 && <ConnectHint what="почта" />}
                        </div>
                        <div>
                            <label className={label}>Кому (адрес электронной почты)</label>
                            <input value={cfg.to ?? ""} onChange={(e) => set({ to: e.target.value })} placeholder="{email_from}" className={input} />
                            <p className="text-xs text-gray-400 mt-1">
                                {"{email_from}"} — отправитель входящего письма. Можно указать конкретный адрес или результат шага «Обработка текста» с найденным email.
                            </p>
                        </div>
                        <div>
                            <label className={label}>Тема письма</label>
                            <input value={cfg.subject ?? ""} onChange={(e) => set({ subject: e.target.value })} placeholder="Re: {email_subject}" className={input} />
                        </div>
                        <div>
                            <label className={label}>Текст письма (результаты других шагов подставляются в фигурных скобках, например {"{reply}"})</label>
                            <textarea value={cfg.body ?? ""} onChange={(e) => set({ body: e.target.value })} rows={6} className={input} />
                        </div>
                        <label className="flex items-center gap-2 text-sm text-gray-700">
                            <input type="checkbox" checked={!!cfg.as_reply} onChange={(e) => set({ as_reply: e.target.checked })} />
                            Отправить как ответ в переписке (работает после шага «Новое письмо»)
                        </label>
                        <ToolSettingsFields key={node.id} cfg={cfg} set={set} preset={TOOL_PRESETS.email_send} />
                    </>
                )}

                {node.type === "text_transform" && (
                    <>
                        <div>
                            <label className={label}>Что сделать с текстом</label>
                            <select value={cfg.operation || "extract_order"} onChange={(e) => set({ operation: e.target.value })} className={input}>
                                {(["Поиск", "Очистка"] as const).map((group) => (
                                    <optgroup key={group} label={group === "Поиск" ? "Найти в тексте" : "Очистить или изменить"}>
                                        {TEXT_OPERATIONS.filter((o) => o.group === group).map((o) => (
                                            <option key={o.id} value={o.id}>
                                                {o.label}
                                            </option>
                                        ))}
                                    </optgroup>
                                ))}
                            </select>
                            <p className="text-xs text-gray-500 mt-1">{OPERATIONS[cfg.operation || "extract_order"]?.hint}</p>
                        </div>
                        <div>
                            <label className={label}>Исходный текст</label>
                            <input value={cfg.value ?? "{input}"} onChange={(e) => set({ value: e.target.value })} className={mono} />
                            <p className="text-xs text-gray-400 mt-1">
                                {"{input}"} — сообщение клиента или текст письма. Можно указать результат другого шага, например {"{reply}"}.
                            </p>
                        </div>
                        {OPERATIONS[cfg.operation || "extract_order"]?.needsPattern && (
                            <div>
                                <label className={label}>Шаблон поиска (регулярное выражение)</label>
                                <input value={cfg.pattern ?? ""} onChange={(e) => set({ pattern: e.target.value })} placeholder="код (\\w+)" className={mono} />
                            </div>
                        )}
                        {OPERATIONS[cfg.operation || "extract_order"]?.needsLength && (
                            <div>
                                <label className={label}>Сколько символов оставить</label>
                                <input type="number" min={1} value={cfg.max_chars ?? 500} onChange={(e) => set({ max_chars: Number(e.target.value) || 500 })} className={input} />
                            </div>
                        )}
                        <p className="text-xs leading-snug text-gray-400">
                            Результат — текст, он доступен в следующих шагах по имени этого шага, например {"{" + node.id + "}"}. Если ничего не найдено, результат будет пустым.
                        </p>
                    </>
                )}

                {node.type === "schedule" && (
                    <>
                        <div>
                            <label className={label}>Интервал, минут</label>
                            <input
                                type="number"
                                min={1}
                                value={cfg.interval_minutes ?? 60}
                                onChange={(e) =>
                                    set({ interval_minutes: Number(e.target.value) || 60 })
                                }
                                className={input}
                            />
                            <p className="text-xs text-gray-400 mt-1">
                                Запускается, пока сценарий включён. В облаке минимум 5 минут. Счётчик сбрасывается при перезапуске сервера.
                            </p>
                        </div>
                        <TestInputField cfg={cfg} set={set} />
                    </>
                )}
            </div>
        </div>
    );
}
