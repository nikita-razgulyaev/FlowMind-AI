export interface LogEntry {
    node_id: string;
    type: string;
    input: Record<string, any>;
    output: any;
}

export interface ExecutionRecord {
    id: number;
    workflow_id: number;
    status: string;
    source?: string;
    trigger_data: Record<string, any> | null;
    logs: LogEntry[] | null;
    started_at: string;
    finished_at: string | null;
}

export function formatDate(iso: string): string {
    try {
        return new Date(iso).toLocaleString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return iso;
    }
}

export interface Line {
    who: string;
    text: string;
    tone: "user" | "agent" | "tool" | "muted";
}

function safeParse(text: string): any {
    try {
        return JSON.parse(text);
    } catch {
        return text;
    }
}

function summarizeHttpBody(body: unknown): string {
    if (typeof body !== "string") return String(body);
    const parsed = safeParse(body);
    if (parsed && typeof parsed === "object") {
        const keys = Object.keys(parsed).slice(0, 3);
        return keys
            .map((k) => `${k}: ${JSON.stringify((parsed as any)[k])}`)
            .join(", ");
    }
    return body.slice(0, 120);
}

export function buildLines(
    triggerInput: string | undefined,
    logs: LogEntry[],
): Line[] {
    const lines: Line[] = [];
    if (triggerInput)
        lines.push({ who: "Пользователь", text: triggerInput, tone: "user" });

    for (const log of logs) {
        if (
            log.type === "agent" &&
            log.output &&
            typeof log.output === "object"
        ) {
            for (const msg of log.output.trace || []) {
                if (msg.role === "assistant") {
                    if (msg.tool_calls?.length) {
                        for (const call of msg.tool_calls) {
                            const args = call.function?.arguments || {};
                            const argsStr = Object.entries(args)
                                .map(([k, v]) => `${k}=${v}`)
                                .join(", ");
                            lines.push({
                                who: "Агент",
                                text: `вызывает ${call.function?.name}(${argsStr})`,
                                tone: "agent",
                            });
                        }
                    }
                    if (msg.content) {
                        lines.push({
                            who: "Агент",
                            text: msg.content,
                            tone: "agent",
                        });
                    }
                } else if (msg.role === "tool") {
                    const parsed = safeParse(msg.content);
                    const summary =
                        parsed && typeof parsed === "object" && "body" in parsed
                            ? summarizeHttpBody(parsed.body)
                            : msg.content;
                    lines.push({
                        who: `Инструмент (${msg.tool_name})`,
                        text: summary,
                        tone: "tool",
                    });
                }
            }
        } else if (log.type === "http") {
            const out = log.output;
            const statusText =
                out && typeof out === "object"
                    ? `status ${out.status_code}`
                    : String(out);
            lines.push({
                who: `HTTP (${log.node_id})`,
                text: statusText,
                tone: "muted",
            });
        } else if (log.type === "print") {
            lines.push({
                who: `Print (${log.node_id})`,
                text: String(log.output),
                tone: "muted",
            });
        } else if (log.type === "email_send") {
            const out = log.output;
            if (out && typeof out === "object" && out.status === "sent") {
                lines.push({
                    who: "Почта",
                    text: `отправлено → ${out.to}${out.subject ? `: ${out.subject}` : ""}`,
                    tone: "tool",
                });
            } else {
                lines.push({
                    who: "Почта",
                    text: String(out ?? "ошибка отправки"),
                    tone: "muted",
                });
            }
        } else if (log.type === "email_trigger") {
            const out = log.output;
            const textOut =
                out && typeof out === "object"
                    ? [out.from || out.email_from, out.subject || out.email_subject, out.body || out.email_body || out.input]
                          .filter(Boolean)
                          .join(" | ")
                    : String(out ?? "");
            if (textOut) {
                lines.push({ who: "Входящее письмо", text: textOut, tone: "user" });
            }
        } else if (log.type === "llm" || log.type === "agent") {
            const out = log.output;
            const textOut =
                typeof out === "string"
                    ? out
                    : out && typeof out === "object" && out.content
                      ? String(out.content)
                      : out != null
                        ? JSON.stringify(out).slice(0, 500)
                        : "";
            if (textOut) {
                lines.push({
                    who: log.type === "agent" ? "Агент" : "ИИ",
                    text: textOut,
                    tone: "agent",
                });
            }
        } else if (log.type === "telegram_send" || log.type === "telegram_trigger") {
            const out = log.output;
            lines.push({
                who: log.type === "telegram_send" ? "Telegram" : "Telegram (вх.)",
                text: typeof out === "string" ? out : out != null ? JSON.stringify(out).slice(0, 300) : "",
                tone: log.type === "telegram_send" ? "tool" : "user",
            });
        } else if (typeof log.output === "string" && log.output) {
            // Общий fallback: ошибки и текстовые результаты (Email Error, LLM Error и т.п.)
            const isErr = /error|ошибк|failed|fail/i.test(log.output);
            lines.push({
                who: log.type || log.node_id,
                text: log.output,
                tone: isErr ? "muted" : "tool",
            });
        } else if (log.output != null && log.output !== "") {
            lines.push({
                who: log.type || log.node_id,
                text: typeof log.output === "object" ? JSON.stringify(log.output).slice(0, 400) : String(log.output),
                tone: "muted",
            });
        }
    }
    return lines;
}

export function extractTriggerInput(
    triggerData: Record<string, any> | null | undefined,
): string | undefined {
    if (!triggerData) return undefined;
    if (typeof triggerData.input === "string") return triggerData.input;
    if (Object.keys(triggerData).length === 0) return undefined;
    return JSON.stringify(triggerData);
}

export interface TextPart {
    text: string;
    bold: boolean;
}

/** Делит текст на куски: **слово** → жирный кусок без звёздочек; одиночные ** без пары остаются как есть. */
export function splitBold(text: string): TextPart[] {
    const parts: TextPart[] = [];
    let last = 0;
    for (const match of text.matchAll(/\*\*(\S(?:[^*]*?\S)?)\*\*/g)) {
        if (match.index! > last) parts.push({ text: text.slice(last, match.index), bold: false });
        parts.push({ text: match[1], bold: true });
        last = match.index! + match[0].length;
    }
    if (last < text.length) parts.push({ text: text.slice(last), bold: false });
    return parts;
}
