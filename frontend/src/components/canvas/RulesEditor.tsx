import { Plus, Trash2 } from "lucide-react";
import { RefInput, RefSelect } from "./RefFields";

export interface Rule {
    value: string;
    /** "auto" — значение следует за предыдущим шагом; "manual" — ручной ввод; "step" — выбран шаг. */
    mode?: string;
    operator: string;
    expected: string;
}

export const OPERATORS: { id: string; label: string; noValue?: boolean }[] = [
    { id: "contains", label: "содержит" },
    { id: "not_contains", label: "не содержит" },
    { id: "equals", label: "равно" },
    { id: "not_equals", label: "не равно" },
    { id: "starts_with", label: "начинается с" },
    { id: "ends_with", label: "заканчивается на" },
    { id: "gt", label: "больше (число)" },
    { id: "gte", label: "больше или равно" },
    { id: "lt", label: "меньше (число)" },
    { id: "lte", label: "меньше или равно" },
    { id: "empty", label: "пусто", noValue: true },
    { id: "not_empty", label: "не пусто", noValue: true },
    { id: "regex", label: "подходит под шаблон" },
];

export const EMPTY_RULE: Rule = { value: "{input}", mode: "auto", operator: "contains", expected: "" };

const field = "w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:outline-hidden focus:ring-blue-500 focus:border-blue-500";

interface Props {
    rules: Rule[];
    match: "all" | "any";
    onChange: (patch: { rules?: Rule[]; match?: "all" | "any" }) => void;
}

/** Условие без кода: правила вида «значение — оператор — с чем сравнить». */
export default function RulesEditor({ rules, match, onChange }: Props) {
    const update = (index: number, patch: Partial<Rule>) => onChange({ rules: rules.map((r, i) => (i === index ? { ...r, ...patch } : r)) });

    return (
        <div className="space-y-2">
            {rules.length > 1 && (
                <div className="flex items-center gap-2 text-xs text-gray-600">
                    Условие выполнено, если подходит
                    <select value={match} onChange={(e) => onChange({ match: e.target.value as "all" | "any" })} className="rounded-lg border border-gray-300 px-2 py-1 text-xs">
                        <option value="all">каждое правило</option>
                        <option value="any">любое правило</option>
                    </select>
                </div>
            )}
            {rules.map((rule, index) => {
                const operator = OPERATORS.find((o) => o.id === rule.operator);
                return (
                    <div key={index} className="space-y-1.5 rounded-lg border border-gray-200 bg-gray-50 p-2">
                        <div className="flex items-start gap-1.5">
                            <div className="min-w-0 flex-1">
                                <RefSelect
                                    value={rule.value}
                                    mode={rule.mode}
                                    onChange={(p) => update(index, p)}
                                    inputClassName={`${field} font-mono`}
                                />
                            </div>
                            <button type="button" onClick={() => onChange({ rules: rules.filter((_, i) => i !== index) })} className="shrink-0 rounded p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-500" title="Удалить правило">
                                <Trash2 className="h-4 w-4" />
                            </button>
                        </div>
                        <select value={rule.operator} onChange={(e) => update(index, { operator: e.target.value })} className={field}>
                            {OPERATORS.map((o) => (
                                <option key={o.id} value={o.id}>
                                    {o.label}
                                </option>
                            ))}
                        </select>
                        {!operator?.noValue && (
                            <RefInput value={rule.expected} onChange={(e) => update(index, { expected: e.target.value })} placeholder="С чем сравнить" className={field} />
                        )}
                    </div>
                );
            })}
            <button type="button" onClick={() => onChange({ rules: [...rules, { ...EMPTY_RULE }] })} className="flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700">
                <Plus className="h-3.5 w-3.5" /> Добавить правило
            </button>
        </div>
    );
}
