import { useEffect, useRef, useState } from "react";
import { ChevronDown, DatabaseZap } from "lucide-react";
import { splitRefs, type DataGroup } from "../../utils/stepData";

export type TextField = HTMLInputElement | HTMLTextAreaElement;

const TEXT_INPUT_TYPES = ["", "text", "url", "search", "email", "tel"];

/** Подходит ли элемент для вставки данных: текстовое поле, не помеченное data-no-insert. */
export function isInsertTarget(el: EventTarget | null): el is TextField {
    if (el instanceof HTMLTextAreaElement) return !el.readOnly && el.dataset.noInsert === undefined;
    if (el instanceof HTMLInputElement) return !el.readOnly && TEXT_INPUT_TYPES.includes(el.type) && el.dataset.noInsert === undefined;
    return false;
}

/** Вставляет текст в позицию курсора так, чтобы React увидел изменение как ввод пользователя. */
function insertAtCursor(el: TextField, token: string) {
    el.focus();
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? start;
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, el.value.slice(0, start) + token + el.value.slice(end));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.setSelectionRange(start + token.length, start + token.length);
}

interface Props {
    /** Последнее выбранное текстовое поле шага. */
    field: TextField | null;
    groups: DataGroup[];
    names: Record<string, string>;
    /** Меняется при каждом вводе — чтобы обновлять подписи ссылок. */
    version: number;
}

/** Строка над настройками шага: кнопка «Вставить данные из шага» и понятные подписи ссылок в выбранном поле. */
export default function DataInsertBar({ field, groups, names, version }: Props) {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const close = (e: MouseEvent) => {
            if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener("mousedown", close);
        return () => document.removeEventListener("mousedown", close);
    }, [open]);

    const pick = (group: DataGroup, path: string) => {
        if (!field) return;
        // Переменные запуска: путь — это само имя ({input}); у шага — id и путь ({id_шага.json.rates})
        insertAtCursor(field, group.id ? `{${group.id}${path}}` : `{${path}}`);
        setOpen(false);
    };

    const segments = field ? splitRefs(field.value, names).filter((s) => s.kind === "ref") : [];
    void version;

    return (
        <div ref={rootRef} className="relative border-b border-gray-100 bg-gray-50 px-4 py-2">
            <button
                type="button"
                disabled={!field}
                onClick={() => setOpen((v) => !v)}
                className="flex items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-2.5 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-400 disabled:hover:bg-white"
            >
                <DatabaseZap className="h-3.5 w-3.5" />
                Вставить данные из шага
                <ChevronDown className="h-3 w-3" />
            </button>
            {!field && <p className="mt-1 text-[11px] text-gray-400">Нажмите на нужное текстовое поле ниже, затем выберите, какие данные в него вставить.</p>}

            {segments.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1">
                    <span className="text-[11px] text-gray-400">В поле:</span>
                    {segments.map((s, i) => (
                        <span
                            key={i}
                            title={s.text}
                            className={`rounded-full px-2 py-0.5 text-[11px] ${s.broken ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-700"}`}
                        >
                            {s.label}
                        </span>
                    ))}
                </div>
            )}

            {open && (
                <div className="absolute left-4 right-4 top-full z-30 mt-1 max-h-80 overflow-y-auto rounded-lg border border-gray-200 bg-white p-1 shadow-xl">
                    {groups.map((group) => (
                        <div key={group.id || "start"} className="py-1">
                            <p className="px-2 pb-0.5 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
                                {group.title}
                                {group.disconnected && <span className="ml-1 font-normal normal-case text-amber-600">· не соединён с этим шагом</span>}
                            </p>
                            {group.fields.map((f) => (
                                <button
                                    key={f.path || "_"}
                                    type="button"
                                    onClick={() => pick(group, f.path)}
                                    className="block w-full rounded px-2 py-1.5 text-left hover:bg-blue-50"
                                >
                                    <span className="block text-xs text-gray-800">{f.label}</span>
                                    {f.sample && <span className="block truncate text-[11px] text-gray-400">например: {f.sample}</span>}
                                </button>
                            ))}
                        </div>
                    ))}
                    {groups.length === 1 && (
                        <p className="px-2 py-2 text-[11px] text-gray-400">
                            Соедините этот шаг с предыдущими, и здесь появятся их данные. После запуска сценария будут видны реальные значения.
                        </p>
                    )}
                </div>
            )}
        </div>
    );
}
