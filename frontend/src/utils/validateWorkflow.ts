import type { Connection, WorkflowEdge, WorkflowNode } from "../types/workflow";
import { REF_PATTERN, START_VARIABLES, configStrings, isTrigger, stepName, upstreamIds } from "./stepData";
import { getBranches } from "../components/canvas/CanvasNode";

export interface StepIssue {
    /** null — проблема всего сценария. */
    nodeId: string | null;
    level: "error" | "warning";
    message: string;
}

const CONNECTION_REQUIRED: Record<string, string> = {
    telegram_trigger: "бота Telegram",
    telegram_send: "бота Telegram",
    email_trigger: "почту",
    email_send: "почту",
    google_sheets_append: "таблицы",
    google_calendar_create_event: "календарь",
};

/** Обязательные поля: [ключ config, как назвать для пользователя]. */
const REQUIRED_FIELDS: Record<string, [string, string][]> = {
    llm: [["prompt", "задание для нейросети"]],
    agent: [["prompt", "задание для агента"]],
    http: [["url", "адрес сервиса"]],
    telegram_send: [["message", "текст сообщения"]],
    email_send: [["body", "текст письма"]],
    google_sheets_append: [["spreadsheet_id", "таблицу"], ["values", "значения для строки"]],
    google_calendar_create_event: [["summary", "название события"], ["start_datetime", "время начала"]],
    switch: [["cases", "варианты"]],
    keyword_switch: [["rules", "категории и слова"]],
    text_assemble: [["template", "шаблон текста"]],
    set: [["values", "значения"]],
};

function missingField(node: WorkflowNode, key: string): boolean {
    const value = node.config?.[key];
    return value === undefined || value === null || String(value).trim() === "";
}

function conditionIncomplete(node: WorkflowNode): boolean {
    const cfg = node.config || {};
    if (cfg.mode === "rules") {
        const rules = Array.isArray(cfg.rules) ? cfg.rules : [];
        return !rules.length || rules.some((r: any) => !String(r.value ?? "").trim() || (!["empty", "not_empty"].includes(r.operator) && !String(r.expected ?? "").trim()));
    }
    return !String(cfg.expression ?? "").trim();
}

/** Проверка сценария до запуска: что не заполнено, не соединено или ссылается на несуществующее. */
export function validateWorkflow(nodes: WorkflowNode[], edges: WorkflowEdge[], connections: Connection[] = []): StepIssue[] {
    const issues: StepIssue[] = [];
    const ids = new Set(nodes.map((n) => n.id));
    const connectionIds = new Set(connections.map((c) => c.id));
    const name = (n: WorkflowNode) => stepName(n, nodes);

    if (!nodes.length) return [{ nodeId: null, level: "error", message: "В сценарии пока нет шагов" }];
    if (!nodes.some((n) => isTrigger(n.type))) {
        issues.push({ nodeId: null, level: "warning", message: "Нет шага запуска: добавьте на вкладке «Запуск», как сценарий должен стартовать" });
    }

    for (const node of nodes) {
        const add = (level: StepIssue["level"], message: string) => issues.push({ nodeId: node.id, level, message });
        const cfg = node.config || {};

        if (!isTrigger(node.type) && !edges.some((e) => e.to_node === node.id)) {
            add("warning", "Шаг ни с чем не соединён: он не получит данные и не выполнится");
        }

        for (const [key, title] of REQUIRED_FIELDS[node.type] ?? []) {
            if (missingField(node, key)) add("error", `Не заполнено: ${title}`);
        }
        if (node.type === "condition" && conditionIncomplete(node)) add("error", "Условие заполнено не полностью");
        if (node.type === "text_transform" && !cfg.operation) add("error", "Не выбрано, что сделать с текстом");

        const needsConnection = CONNECTION_REQUIRED[node.type];
        if (needsConnection) {
            if (!cfg.connection_id) add("error", `Не выбрано подключение: ${needsConnection}`);
            else if (connections.length && !connectionIds.has(cfg.connection_id)) add("error", "Выбранное подключение удалено: выберите другое");
        }

        const upstream = new Set(upstreamIds(node.id, edges));
        const reported = new Set<string>();
        for (const text of configStrings(cfg)) {
            for (const match of text.matchAll(REF_PATTERN)) {
                const ref = match[1];
                if (reported.has(ref) || ref in START_VARIABLES) continue;
                reported.add(ref);
                if (!ids.has(ref)) {
                    add("error", `Ссылка {${ref}} ведёт на несуществующий шаг. Выберите данные через «Вставить данные из шага»`);
                } else if (ref !== node.id && !upstream.has(ref) && edges.length) {
                    const source = nodes.find((n) => n.id === ref)!;
                    add("warning", `Шаг «${name(source)}» не соединён с этим шагом выше по цепочке: его данные могут быть ещё не готовы`);
                } else if (ref === node.id) {
                    add("error", "Шаг ссылается на собственный результат");
                }
            }
        }

        const branches = getBranches(node.type, cfg);
        for (const branch of branches) {
            if (!edges.some((e) => e.from_node === node.id && e.condition === branch)) {
                add("warning", `Нет следующего шага для ветки «${branch}»: при таком результате сценарий на этом закончится`);
            }
        }
    }
    return issues;
}

export function issuesByNode(issues: StepIssue[]): Record<string, StepIssue[]> {
    const map: Record<string, StepIssue[]> = {};
    for (const issue of issues) if (issue.nodeId) (map[issue.nodeId] ||= []).push(issue);
    return map;
}
