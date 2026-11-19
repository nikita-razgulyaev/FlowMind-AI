import type { WorkflowEdge, WorkflowNode } from "../types/workflow";
import { NODE_INFO } from "./glossary";

/** Ссылка на данные: {имя} или {имя.путь.к.полю} (совпадает с PLACEHOLDER_RE на сервере). */
export const REF_PATTERN = /\{([A-Za-z_][\w-]*)((?:\.[\w-]+|\[\d+\])*)\}/g;

export interface DataField {
    /** Путь внутри результата шага: "" — весь результат, ".json.rates.RUB" — поле. */
    path: string;
    label: string;
    sample?: string;
}

export interface DataGroup {
    /** Что подставлять перед путём: id шага или имя переменной запуска. */
    id: string;
    title: string;
    fields: DataField[];
    /** Группа — шаг запуска: его «поля» это переменные запуска ({input}, {email_subject}), а не пути внутри результата. */
    trigger?: boolean;
    /** Шаг не соединён с текущим: в списке показывается пометка «не соединён с этим шагом». */
    disconnected?: boolean;
}

/** Переменные, которые есть в сценарии без отдельного шага: данные запуска. */
export const START_VARIABLES: Record<string, string> = {
    input: "Текст запуска (сообщение, письмо, тест)",
    telegram_text: "Текст сообщения Telegram",
    telegram_chat_id: "Чат клиента в Telegram",
    telegram_username: "Логин клиента в Telegram",
    telegram_first_name: "Имя клиента в Telegram",
    email_from: "Адрес отправителя письма",
    email_from_name: "Имя отправителя письма",
    email_subject: "Тема письма",
    email_body: "Текст письма",
    email_message_id: "Номер письма",
    webhook: "Данные вызова по ссылке",
    last_result: "Результат последнего шага",
};

const TRIGGER_FIELDS: Record<string, string[]> = {
    manual: ["input"],
    schedule: ["input"],
    telegram_trigger: ["input", "telegram_chat_id", "telegram_username", "telegram_first_name"],
    email_trigger: ["input", "email_from", "email_from_name", "email_subject", "email_body"],
    webhook: ["input", "webhook"],
};

const TRIGGER_TYPES = Object.keys(TRIGGER_FIELDS);
const SIMPLE_RESULT_TYPES = ["text_transform", "text_assemble", "text_input", "keyword_switch", "switch", "condition", "print", "llm"];

export function isTrigger(type: string): boolean {
    return TRIGGER_TYPES.includes(type);
}

/** Понятное название шага: заданное пользователем или «Тип» (с номером, если таких шагов несколько). */
export function stepName(node: Pick<WorkflowNode, "id" | "type" | "config">, all: Pick<WorkflowNode, "id" | "type">[]): string {
    const custom = String(node.config?.step_name ?? "").trim();
    if (custom) return custom;
    const base = NODE_INFO[node.type]?.label ?? node.type;
    const same = all.filter((n) => n.type === node.type);
    return same.length > 1 ? `${base} ${same.findIndex((n) => n.id === node.id) + 1}` : base;
}

export function buildNames(nodes: WorkflowNode[]): Record<string, string> {
    return Object.fromEntries(nodes.map((n) => [n.id, stepName(n, nodes)]));
}

function pathLabel(path: string): string {
    return path.replace(/^\./, "").replace(/\./g, " → ").replace(/\[(\d+)\]/g, " №$1") || "результат";
}

function sampleOf(value: unknown): string {
    const text = typeof value === "string" ? value : JSON.stringify(value);
    return (text ?? "").replace(/\s+/g, " ").slice(0, 60);
}

/** Раскладывает реальный результат шага на поля: объект → ключи, список → первые элементы. */
export function flattenOutput(value: unknown, path = "", depth = 0, out: DataField[] = []): DataField[] {
    if (out.length >= 40) return out;
    if (value !== null && typeof value === "object" && depth < 4) {
        const entries = Array.isArray(value)
            ? value.slice(0, 3).map((v, i) => [`[${i}]`, v] as const)
            : Object.entries(value as Record<string, unknown>).map(([k, v]) => [`.${k}`, v] as const);
        for (const [key, child] of entries) {
            if (!/^(\.[\w-]+|\[\d+\])$/.test(key)) continue;        // ключи с пробелами в путь не подставить
            flattenOutput(child, path + key, depth + 1, out);
        }
        return out;
    }
    out.push({ path, label: pathLabel(path), sample: sampleOf(value) });
    return out;
}

function staticFields(node: WorkflowNode): DataField[] {
    switch (node.type) {
        case "http":
            return [
                { path: ".json", label: "Данные ответа сервиса (JSON)" },
                { path: ".body", label: "Текст ответа сервиса" },
                { path: ".status_code", label: "Код ответа сервиса" },
            ];
        case "agent":
            return [{ path: ".answer", label: "Ответ агента" }];
        case "set":
            return String(node.config?.values ?? "")
                .split("\n")
                .map((line) => line.split("=")[0].trim())
                .filter((key) => /^[\w-]+$/.test(key))
                .map((key) => ({ path: `.${key}`, label: key }));
        default:
            return SIMPLE_RESULT_TYPES.includes(node.type) ? [{ path: "", label: node.type === "llm" ? "Ответ нейросети" : "Результат шага" }] : [];
    }
}

/** Поля шага для выбора: известные заранее + реальные из последнего запуска (с примерами значений). */
export function fieldsForStep(node: WorkflowNode, output?: unknown): DataField[] {
    const fields = staticFields(node);
    if (output === undefined) return fields;
    const real = flattenOutput(output);
    const merged: DataField[] = fields.map((f) => ({ ...f, sample: real.find((r) => r.path === f.path)?.sample ?? f.sample }));
    for (const r of real) {
        if (r.path !== "" && !merged.some((f) => f.path === r.path)) merged.push(r);
    }
    if (typeof output !== "object" && !merged.length) merged.push({ path: "", label: "Результат шага", sample: sampleOf(output) });
    return merged;
}

/** Шаги, чьи данные готовы к моменту выполнения `nodeId`: все, кто выше по связям (ближние первыми). */
export function upstreamIds(nodeId: string, edges: WorkflowEdge[]): string[] {
    const seen: string[] = [];
    let frontier = [nodeId];
    while (frontier.length) {
        const next: string[] = [];
        for (const id of frontier) {
            for (const e of edges) {
                if (e.to_node === id && e.type !== "tool" && e.from_node !== nodeId && !seen.includes(e.from_node)) {
                    seen.push(e.from_node);
                    next.push(e.from_node);
                }
            }
        }
        frontier = next;
    }
    return seen;
}

/** Группы данных для выбора в шаге `nodeId`: только шаги, соединённые с ним выше по цепочке; ближайший (предыдущий) первым. */
export function buildDataGroups(
    nodeId: string,
    nodes: WorkflowNode[],
    edges: WorkflowEdge[],
    outputs: Record<string, unknown>,
): DataGroup[] {
    const names = buildNames(nodes);
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const groups: DataGroup[] = [];
    for (const id of upstreamIds(nodeId, edges)) {
        const node = byId[id];
        if (!node || id === nodeId) continue;
        if (isTrigger(node.type)) {
            const fields = TRIGGER_FIELDS[node.type].map((key) => ({ path: key, label: START_VARIABLES[key] ?? key }));
            groups.push({ id, title: names[id], fields, trigger: true });
            continue;
        }
        const fields = fieldsForStep(node, outputs[id]);
        groups.push({ id, title: names[id], fields: fields.length ? fields : [{ path: "", label: "Результат шага" }] });
    }
    return groups;
}

/** Текст ссылки на поле: переменные запуска — {input}, остальное — {id_шага.путь}. */
export function fieldToken(group: DataGroup, field: DataField): string {
    return group.trigger ? `{${field.path}}` : `{${group.id}${field.path}}`;
}

/** Ссылка на данные предыдущего шага (по умолчанию для новых полей) или null, если шаг ни с чем не соединён. */
export function defaultRefToken(nodeId: string, nodes: WorkflowNode[], edges: WorkflowEdge[]): string | null {
    const [previous] = buildDataGroups(nodeId, nodes, edges, {});
    return previous ? fieldToken(previous, previous.fields[0]) : null;
}

const FULL_REF = /^\{([A-Za-z_][\w-]*)((?:\.[\w-]+|\[\d+\])*)\}$/;

export interface RefSelection {
    kind: "none" | "step" | "manual";
    groupId?: string;
    /** Путь внутри результата шага (для переменных запуска — имя переменной). */
    path?: string;
}

/**
 * Что показать в выпадающем списке для сохранённого значения.
 * mode: "auto" — следует за предыдущим шагом, "manual" — ручной ввод, "step" или не задан — по самому значению.
 */
export function resolveRefSelection(value: string, mode: string | undefined, groups: DataGroup[]): RefSelection {
    if (mode === "manual") return { kind: "manual" };
    if (mode === "auto") {
        return groups.length ? { kind: "step", groupId: groups[0].id, path: groups[0].fields[0].path } : { kind: "none" };
    }
    const match = FULL_REF.exec(value.trim());
    if (match) {
        const [, name, path] = match;
        const direct = groups.find((g) => !g.trigger && g.id === name);
        if (direct) return { kind: "step", groupId: direct.id, path };
        const trigger = groups.find((g) => g.trigger && !path && g.fields.some((f) => f.path === name));
        if (trigger) return { kind: "step", groupId: trigger.id, path: name };
    }
    if (!value.trim() && !groups.length) return { kind: "none" };
    return { kind: "manual" };
}

export interface TextSegment {
    kind: "text" | "ref";
    text: string;
    /** Для ссылки: понятная подпись. */
    label?: string;
    /** Ссылка ведёт на несуществующий шаг. */
    broken?: boolean;
}

/** Делит текст на обычные куски и ссылки с понятными подписями. */
export function splitRefs(text: string, names: Record<string, string>): TextSegment[] {
    const result: TextSegment[] = [];
    let last = 0;
    for (const match of text.matchAll(REF_PATTERN)) {
        const [raw, name, path] = match;
        const index = match.index ?? 0;
        if (index > last) result.push({ kind: "text", text: text.slice(last, index) });
        const title = names[name] ?? START_VARIABLES[name];
        result.push({
            kind: "ref",
            text: raw,
            broken: !title,
            label: title ? (path ? `${title} → ${pathLabel(path)}` : title) : `нет шага «${name}»`,
        });
        last = index + raw.length;
    }
    if (last < text.length) result.push({ kind: "text", text: text.slice(last) });
    return result;
}

/** Текст с понятными подписями вместо {id.путь}: для коротких превью на карточках. */
export function humanizeText(text: string, names: Record<string, string>): string {
    if (!text.includes("{")) return text;
    return splitRefs(text, names)
        .map((s) => (s.kind === "ref" && !s.broken ? `[${s.label}]` : s.text))
        .join("");
}

/** Все строки внутри config (включая вложенные списки правил). */
export function configStrings(value: unknown): string[] {
    if (typeof value === "string") return [value];
    if (Array.isArray(value)) return value.flatMap(configStrings);
    if (value && typeof value === "object") return Object.values(value).flatMap(configStrings);
    return [];
}
