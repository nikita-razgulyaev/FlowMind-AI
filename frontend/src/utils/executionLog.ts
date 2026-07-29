export interface LogEntry {
    node_id: string;
    type: string;
    input: Record<string, any>;
    output: any;
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
