import { createContext, useContext, useRef, useState, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { fieldToken, resolveRefSelection, splitRefs, type DataField, type DataGroup } from "../../utils/stepData";

/** Данные, которые можно подставить в поля текущего шага: шаги, соединённые с ним выше по цепочке (предыдущий — первым). */
export const DataPickerContext = createContext<{ groups: DataGroup[]; names: Record<string, string> }>({ groups: [], names: {} });

type TextField = HTMLInputElement | HTMLTextAreaElement;

const selectClass =
    "min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-700 focus:border-blue-500 focus:ring-2 focus:outline-hidden focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400";
const NONE_LABEL = "Нет соединённых шагов";
const MANUAL_LABEL = "Ручной ввод";

/** Вставляет текст в позицию курсора так, чтобы React увидел изменение как ввод пользователя. */
function insertText(el: TextField, token: string, range: { start: number; end: number } | null) {
    const start = range?.start ?? el.value.length;
    const end = range?.end ?? start;
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, el.value.slice(0, start) + token + el.value.slice(end));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.focus();
    el.setSelectionRange(start + token.length, start + token.length);
}

/** Поля шага: заранее известные; если сохранённого пути среди них нет (например, .json.rates.RUB), он добавляется отдельным пунктом. */
function fieldsWithPath(group: DataGroup, path: string | undefined): DataField[] {
    if (path === undefined || group.fields.some((f) => f.path === path)) return group.fields;
    return [...group.fields, { path, label: path.replace(/^\./, "").replace(/\./g, " → ") }];
}

function RefField({ multiline, ...props }: { multiline: boolean } & (InputHTMLAttributes<HTMLInputElement> & TextareaHTMLAttributes<HTMLTextAreaElement>)) {
    const { groups, names } = useContext(DataPickerContext);
    const fieldRef = useRef<TextField>(null);
    const caret = useRef<{ start: number; end: number } | null>(null);
    const [groupId, setGroupId] = useState<string | null>(null);
    const [path, setPath] = useState<string | null>(null);

    const group = groups.find((g) => g.id === groupId) ?? groups[0];
    const field = group?.fields.find((f) => f.path === path) ?? group?.fields[0];

    const remember = () => {
        const el = fieldRef.current;
        if (el) caret.current = { start: el.selectionStart ?? el.value.length, end: el.selectionEnd ?? el.value.length };
    };
    const insert = () => {
        if (!group || !field || !fieldRef.current) return;
        insertText(fieldRef.current, fieldToken(group, field), caret.current);
        caret.current = null;
    };

    const { onBlur, ...rest } = props;
    const shared = {
        ...rest,
        onBlur: (e: React.FocusEvent<never>) => {
            remember();
            (onBlur as ((e: React.FocusEvent<never>) => void) | undefined)?.(e);
        },
    };
    const refs = splitRefs(String(props.value ?? ""), names).filter((s) => s.kind === "ref");

    return (
        <div>
            {multiline ? (
                <textarea ref={fieldRef as React.RefObject<HTMLTextAreaElement>} {...shared} />
            ) : (
                <input ref={fieldRef as React.RefObject<HTMLInputElement>} {...shared} />
            )}
            <div className="mt-1.5 flex items-center gap-1.5">
                <select
                    value={group?.id ?? ""}
                    disabled={!group}
                    onChange={(e) => {
                        setGroupId(e.target.value);
                        setPath(null);
                    }}
                    title="Шаг, данные которого нужно вставить в текст"
                    className={selectClass}
                >
                    {!group && <option value="">{NONE_LABEL}</option>}
                    {groups.map((g) => (
                        <option key={g.id} value={g.id}>
                            {g.title}
                        </option>
                    ))}
                </select>
                {group && group.fields.length > 1 && (
                    <select value={field?.path ?? ""} onChange={(e) => setPath(e.target.value)} title="Какие данные вставить" className={selectClass}>
                        {group.fields.map((f) => (
                            <option key={f.path || "_"} value={f.path}>
                                {f.label}
                            </option>
                        ))}
                    </select>
                )}
                <button
                    type="button"
                    disabled={!group}
                    onMouseDown={remember}
                    onClick={insert}
                    className="shrink-0 rounded-lg border border-blue-200 bg-white px-2.5 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-400 disabled:hover:bg-white"
                >
                    Вставить
                </button>
            </div>
            {refs.length > 0 && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    {refs.map((s, i) => (
                        <span key={i} title={s.text} className={`rounded-full px-2 py-0.5 text-[11px] ${s.broken ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-700"}`}>
                            {s.label}
                        </span>
                    ))}
                </div>
            )}
        </div>
    );
}

/** Однострочное поле; под ним выбор шага (по умолчанию предыдущий) и кнопка «Вставить». */
export function RefInput(props: InputHTMLAttributes<HTMLInputElement>) {
    return <RefField multiline={false} {...(props as object)} />;
}

/** Многострочное поле; под ним выбор шага (по умолчанию предыдущий) и кнопка «Вставить». */
export function RefTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
    return <RefField multiline {...(props as object)} />;
}

interface RefSelectProps {
    value: string;
    /** "auto" — следует за предыдущим шагом, "manual" — ручной ввод, "step" — выбран шаг. */
    mode?: string;
    onChange: (patch: { value: string; mode: "auto" | "manual" | "step" }) => void;
    inputClassName: string;
}

/** Поле, в котором нужна только ссылка на данные: выбор шага из списка или «Ручной ввод» с обычным полем ниже. */
export function RefSelect({ value, mode, onChange, inputClassName }: RefSelectProps) {
    const { groups } = useContext(DataPickerContext);
    const selection = resolveRefSelection(value, mode, groups);
    const group = groups.find((g) => g.id === selection.groupId);
    const fields = group ? fieldsWithPath(group, selection.path) : [];

    const selectValue = selection.kind === "manual" ? "__manual" : selection.kind === "none" ? "__none" : (group?.id ?? "__none");

    const pickGroup = (id: string) => {
        if (id === "__manual") {
            onChange({ value: value.trim() ? value : "{input}", mode: "manual" });
            return;
        }
        const next = groups.find((g) => g.id === id);
        if (next) onChange({ value: fieldToken(next, next.fields[0]), mode: "step" });
    };

    return (
        <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
                <select value={selectValue} onChange={(e) => pickGroup(e.target.value)} className={selectClass}>
                    {selection.kind === "none" && (
                        <option value="__none" disabled>
                            {NONE_LABEL}
                        </option>
                    )}
                    {groups.map((g) => (
                        <option key={g.id} value={g.id}>
                            {g.title}
                        </option>
                    ))}
                    <option value="__manual">{MANUAL_LABEL}</option>
                </select>
                {group && fields.length > 1 && selection.kind === "step" && (
                    <select
                        value={selection.path ?? ""}
                        onChange={(e) => {
                            const picked = fields.find((f) => f.path === e.target.value);
                            if (picked) onChange({ value: fieldToken(group, picked), mode: "step" });
                        }}
                        className={selectClass}
                    >
                        {fields.map((f) => (
                            <option key={f.path || "_"} value={f.path}>
                                {f.label}
                            </option>
                        ))}
                    </select>
                )}
            </div>
            {selection.kind === "manual" && (
                <input value={value} onChange={(e) => onChange({ value: e.target.value, mode: "manual" })} placeholder="{input}" className={inputClassName} />
            )}
        </div>
    );
}
