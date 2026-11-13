import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

const label = "block text-xs font-medium text-gray-500 mb-1";
const input =
    "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500";
const mono = `${input} font-mono`;

export interface ToolParam {
    name: string;
    description: string;
    examples: string[];
    required: boolean;
}

/** Готовый связный пример: название, описание и параметры подходят друг к другу и к полям шага. */
type EditableRow = ToolParam & { examplesText: string };

export interface ToolPreset {
    name: string;
    description: string;
    params: ToolParam[];
}

export const TOOL_PRESETS: Record<string, ToolPreset> = {
    http: {
        name: "get_order_status",
        description: "Получить актуальный статус заказа по его ID",
        params: [{ name: "order_id", description: "Уникальный идентификатор заказа", examples: ["1234", "№1234 от 05.11.26"], required: true }],
    },
    telegram_send: {
        name: "send_telegram_message",
        description: "Отправить сообщение клиенту в Telegram",
        params: [
            { name: "chat_id", description: "Идентификатор чата клиента", examples: ["123456789"], required: true },
            { name: "message", description: "Текст сообщения для клиента", examples: ["Ваш заказ отправлен"], required: true },
        ],
    },
    google_sheets_append: {
        name: "save_client_request",
        description: "Записать обращение клиента в таблицу",
        params: [
            { name: "client_name", description: "Имя клиента", examples: ["Анна"], required: true },
            { name: "phone", description: "Телефон клиента", examples: ["+7 900 111-22-33"], required: false },
            { name: "order_id", description: "Номер заказа, если клиент его назвал", examples: ["1234", "№1234 от 05.11.26"], required: false },
        ],
    },
    google_calendar_create_event: {
        name: "book_appointment",
        description: "Записать клиента на встречу в календарь",
        params: [
            { name: "client_name", description: "Имя клиента", examples: ["Анна"], required: true },
            { name: "start_datetime", description: "Начало встречи, формат ISO 8601", examples: ["2026-11-12T16:00:00+03:00"], required: true },
            { name: "end_datetime", description: "Окончание встречи, формат ISO 8601", examples: ["2026-11-12T17:00:00+03:00"], required: true },
        ],
    },
    email_send: {
        name: "send_email",
        description: "Отправить клиенту письмо на электронную почту",
        params: [
            { name: "to", description: "Адрес электронной почты получателя", examples: ["client@example.com"], required: true },
            { name: "subject", description: "Тема письма", examples: ["Статус Вашего заказа"], required: true },
            { name: "body", description: "Текст письма", examples: ["Здравствуйте! Ваш заказ отправлен."], required: true },
        ],
    },
};

/** JSON Schema из списка параметров. */
export function paramsToSchema(params: ToolParam[]) {
    const properties: Record<string, any> = {};
    for (const p of params) {
        if (!p.name.trim()) continue;
        const prop: Record<string, any> = { type: "string" };
        if (p.description.trim()) prop.description = p.description.trim();
        const examples = p.examples.map((e) => e.trim()).filter(Boolean);
        if (examples.length) prop.examples = examples;
        properties[p.name.trim()] = prop;
    }
    return {
        type: "object",
        properties,
        required: params.filter((p) => p.required && p.name.trim()).map((p) => p.name.trim()),
    };
}

/** Список параметров из схемы; null — схему нельзя показать в простом виде (не только строки). */
export function schemaToParams(schema: any): ToolParam[] | null {
    if (!schema || typeof schema !== "object" || typeof schema.properties !== "object" || schema.properties === null) return null;
    const required: string[] = Array.isArray(schema.required) ? schema.required : [];
    const out: ToolParam[] = [];
    for (const [name, prop] of Object.entries<any>(schema.properties)) {
        if (!prop || typeof prop !== "object" || (prop.type && prop.type !== "string")) return null;
        const extra = Object.keys(prop).filter((k) => !["type", "description", "examples"].includes(k));
        if (extra.length) return null;
        out.push({
            name,
            description: String(prop.description ?? ""),
            examples: Array.isArray(prop.examples) ? prop.examples.map(String) : [],
            required: required.includes(name),
        });
    }
    return out;
}

export default function ToolSettingsFields({
    cfg,
    set,
    preset,
}: {
    cfg: Record<string, any>;
    set: (patch: Record<string, any>) => void;
    preset: ToolPreset;
}) {
    const initial = cfg.tool_parameters ?? paramsToSchema(preset.params);
    const initialRows = typeof initial === "string" ? null : schemaToParams(initial);
    const toEditable = (list: ToolParam[]): EditableRow[] => list.map((p) => ({ ...p, examplesText: p.examples.join("; ") }));
    // Строки хранятся локально: пустые строки и набираемый текст не должны пропадать при пересборке схемы
    const [rows, setRows] = useState<EditableRow[] | null>(initialRows && toEditable(initialRows));
    const [jsonMode, setJsonMode] = useState(false);
    const [jsonText, setJsonText] = useState(typeof initial === "string" ? initial : JSON.stringify(initial, null, 2));
    const [jsonError, setJsonError] = useState(false);
    const showJson = jsonMode || rows === null;

    const commitRows = (next: EditableRow[]) => {
        setRows(next);
        const schema = paramsToSchema(next.map((r) => ({ ...r, examples: r.examplesText.split(";") })));
        set({ tool_parameters: schema });
        setJsonText(JSON.stringify(schema, null, 2));
    };
    const updateRow = (index: number, patch: Partial<EditableRow>) =>
        commitRows((rows ?? []).map((r, i) => (i === index ? { ...r, ...patch } : r)));
    const applyPreset = () => {
        set({ tool_name: preset.name, tool_description: preset.description });
        commitRows(toEditable(preset.params));
        setJsonError(false);
    };
    const editJson = (text: string) => {
        setJsonText(text);
        try {
            const parsed = JSON.parse(text);
            setJsonError(false);
            set({ tool_parameters: parsed });
            const parsedRows = schemaToParams(parsed);
            setRows(parsedRows && toEditable(parsedRows));
        } catch {
            setJsonError(true);
        }
    };

    return (
        <div className="pt-3 border-t border-gray-100 space-y-3">
            <div>
                <p className="text-sm font-semibold text-gray-700">Инструмент для ИИ-агента</p>
                <p className="mt-0.5 text-xs leading-snug text-gray-400">
                    Заполните, только если этот шаг подключён к ИИ-агенту: так агент поймёт, что делает шаг и какие данные ему нужны. Если шаг
                    стоит в обычной цепочке, раздел можно не заполнять.
                </p>
            </div>

            <div>
                <label className={label}>Название инструмента (латиницей, без пробелов)</label>
                <input
                    value={cfg.tool_name || ""}
                    onChange={(e) => set({ tool_name: e.target.value })}
                    placeholder={preset.name}
                    className={mono}
                />
            </div>
            <div>
                <label className={label}>Описание для нейросети: что делает инструмент и когда его вызывать</label>
                <input
                    value={cfg.tool_description || ""}
                    onChange={(e) => set({ tool_description: e.target.value })}
                    placeholder={preset.description}
                    className={input}
                />
            </div>

            <div>
                <div className="mb-1 flex items-center justify-between">
                    <label className={`${label} mb-0`}>Какие данные нужны от клиента</label>
                    <button
                        type="button"
                        onClick={applyPreset}
                        className="text-xs text-blue-600 hover:underline"
                    >
                        Подставить пример
                    </button>
                </div>

                {!showJson && rows && (
                    <div className="space-y-2">
                        {rows.map((row, index) => (
                            <div key={index} className="rounded-lg border border-gray-200 bg-gray-50 p-2 space-y-1.5">
                                <div className="flex items-center gap-2">
                                    <input
                                        value={row.name}
                                        onChange={(e) => updateRow(index, { name: e.target.value })}
                                        placeholder="order_id"
                                        aria-label="Имя поля"
                                        className={`${mono} !py-1`}
                                    />
                                    <label className="flex shrink-0 items-center gap-1 text-xs text-gray-600">
                                        <input type="checkbox" checked={row.required} onChange={(e) => updateRow(index, { required: e.target.checked })} />
                                        обязательно
                                    </label>
                                    <button
                                        type="button"
                                        onClick={() => commitRows(rows.filter((_, i) => i !== index))}
                                        title="Удалить поле"
                                        className="p-1 text-gray-400 hover:text-red-500"
                                    >
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </button>
                                </div>
                                <input
                                    value={row.description}
                                    onChange={(e) => updateRow(index, { description: e.target.value })}
                                    placeholder="Что это за данные, например: Уникальный идентификатор заказа"
                                    aria-label="Описание поля"
                                    className={`${input} !py-1`}
                                />
                                <input
                                    value={row.examplesText}
                                    onChange={(e) => updateRow(index, { examplesText: e.target.value })}
                                    placeholder="Как клиенты пишут это в сообщениях (через «;»): 1234; №1234 от 05.11.26"
                                    aria-label="Примеры значений"
                                    className={`${input} !py-1`}
                                />
                            </div>
                        ))}
                        <button
                            type="button"
                            onClick={() => commitRows([...rows, { name: "", description: "", examples: [], required: false, examplesText: "" }])}
                            className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
                        >
                            <Plus className="h-3.5 w-3.5" /> Добавить поле
                        </button>
                        <p className="text-xs leading-snug text-gray-400">
                            Примеры помогают нейросети находить значение в сообщении клиента, например «Где мой заказ? Его номер 1234».
                            Имя поля можно использовать в настройках шага в фигурных скобках, например {"{order_id}"}.
                        </p>
                    </div>
                )}

                {showJson && (
                    <>
                        <textarea
                            value={jsonText}
                            onChange={(e) => editJson(e.target.value)}
                            rows={9}
                            spellCheck={false}
                            className={mono}
                        />
                        {jsonError && <p className="mt-1 text-xs text-red-600">Некорректный JSON: исправьте запись или нажмите «Подставить пример». Пока ошибка не исправлена, сохраняется последний корректный вариант.</p>}
                    </>
                )}

                {rows !== null && (
                    <button type="button" onClick={() => setJsonMode((v) => !v)} className="mt-2 text-xs text-gray-400 hover:text-gray-600 hover:underline">
                        {jsonMode ? "Вернуться к простому виду" : "Для опытных: показать JSON-схему"}
                    </button>
                )}
            </div>
        </div>
    );
}
