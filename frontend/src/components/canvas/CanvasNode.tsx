import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
    Play,
    Clock,
    Sparkles,
    Globe,
    GitBranch,
    Terminal,
    Bot,
    Send,
    Table,
    CalendarPlus,
} from "lucide-react";

export const NODE_META: Record<
    string,
    { label: string; icon: typeof Play; badge: string; ring: string }
> = {
    manual: {
        label: "Manual Trigger",
        icon: Play,
        badge: "bg-emerald-100 text-emerald-700",
        ring: "border-emerald-200",
    },
    schedule: {
        label: "Schedule",
        icon: Clock,
        badge: "bg-purple-100 text-purple-700",
        ring: "border-purple-200",
    },
    llm: {
        label: "AI / LLM",
        icon: Sparkles,
        badge: "bg-blue-100 text-blue-700",
        ring: "border-blue-200",
    },
    http: {
        label: "HTTP Request",
        icon: Globe,
        badge: "bg-orange-100 text-orange-700",
        ring: "border-orange-200",
    },
    condition: {
        label: "Condition",
        icon: GitBranch,
        badge: "bg-yellow-100 text-yellow-700",
        ring: "border-yellow-200",
    },
    print: {
        label: "Print Output",
        icon: Terminal,
        badge: "bg-gray-100 text-gray-700",
        ring: "border-gray-200",
    },
    agent: {
        label: "Agent",
        icon: Bot,
        badge: "bg-indigo-100 text-indigo-700",
        ring: "border-indigo-200",
    },
    telegram_send: {
        label: "Telegram Send",
        icon: Send,
        badge: "bg-sky-100 text-sky-700",
        ring: "border-sky-200",
    },
    google_sheets_append: {
        label: "Google Sheets",
        icon: Table,
        badge: "bg-green-100 text-green-700",
        ring: "border-green-200",
    },
    google_calendar_create_event: {
        label: "Google Calendar",
        icon: CalendarPlus,
        badge: "bg-red-100 text-red-700",
        ring: "border-red-200",
    },
};

function preview(type: string, config: Record<string, any>): string {
    switch (type) {
        case "llm":
            return config.prompt || "no prompt";
        case "http":
            return (
                `${config.method || "GET"} ${config.url || ""}`.trim() ||
                "no url"
            );
        case "condition":
            return config.expression || "True";
        case "print":
            return config.value || "{last_result}";
        case "agent":
            return config.system_prompt || "no system prompt";
        case "telegram_send":
            return config.chat_id ? `→ ${config.chat_id}` : "no chat_id";
        case "google_sheets_append":
            return config.spreadsheet_id
                ? `→ ${config.spreadsheet_id.slice(0, 20)}...`
                : "no spreadsheet_id";
        case "google_calendar_create_event":
            return config.summary || "no summary";
        default:
            return "";
    }
}

export default function CanvasNode({ id, type, data, selected }: NodeProps) {
    const meta = NODE_META[type as string] ?? NODE_META.print;
    const Icon = meta.icon;
    const config = (data?.config as Record<string, any>) || {};
    const text = preview(type as string, config);
    const isTrigger = type === "manual" || type === "schedule";
    const isAgent = type === "agent";

    return (
        <div
            className={`relative w-64 rounded-xl border-2 bg-white shadow-sm ${
                selected ? "border-blue-400 shadow-md" : meta.ring
            }`}
        >
            {!isTrigger && (
                <Handle
                    type="target"
                    position={Position.Left}
                    id="in"
                    className="!w-2.5 !h-2.5 !bg-gray-400"
                />
            )}

            <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100">
                <span
                    className={`w-7 h-7 rounded-lg flex items-center justify-center ${meta.badge}`}
                >
                    <Icon className="w-4 h-4" />
                </span>
                <span className="text-sm font-semibold text-gray-800">
                    {meta.label}
                </span>
                <span className="ml-auto text-[10px] font-mono text-gray-400">
                    {id}
                </span>
            </div>

            {text && (
                <div
                    className="px-3 py-2 text-xs text-gray-500 font-mono truncate"
                    title={text}
                >
                    {text}
                </div>
            )}

            <Handle
                type="source"
                position={Position.Right}
                id="out-next"
                style={isAgent ? { top: "38%" } : undefined}
                className="!w-2.5 !h-2.5 !bg-blue-500"
            />

            {isAgent && (
                <Handle
                    type="source"
                    position={Position.Bottom}
                    id="out-tool"
                    className="!w-2.5 !h-2.5 !bg-indigo-500"
                />
            )}
            {isAgent && (
                <div className="absolute -bottom-5 left-0 right-0 text-center text-[10px] text-indigo-500 font-medium">
                    ↓ инструменты
                </div>
            )}
        </div>
    );
}
