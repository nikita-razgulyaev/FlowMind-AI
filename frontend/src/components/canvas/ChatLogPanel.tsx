import { X } from "lucide-react";
import { buildLines, type LogEntry } from "../../utils/executionLog";

interface Props {
    triggerInput?: string;
    logs: LogEntry[];
    onClose: () => void;
}

const TONE_STYLES: Record<string, string> = {
    user: "text-gray-500",
    agent: "text-indigo-700 font-medium",
    tool: "text-emerald-700 font-medium",
    muted: "text-gray-400",
};

export default function ChatLogPanel({ triggerInput, logs, onClose }: Props) {
    const lines = buildLines(triggerInput, logs);

    return (
        <div className="border-t border-gray-200 bg-white max-h-56 overflow-y-auto">
            <div className="flex items-center justify-between px-4 py-2 sticky top-0 bg-white border-b border-gray-100">
                <span className="text-xs font-semibold text-gray-500">
                    Чат-лог выполнения
                </span>
                <button
                    onClick={onClose}
                    className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>
            <div className="px-4 py-2 space-y-1.5">
                {lines.length === 0 && (
                    <p className="text-xs text-gray-400">
                        Пока нет данных — запусти workflow (Run).
                    </p>
                )}
                {lines.map((line, i) => (
                    <div key={i} className="text-xs">
                        <span className={TONE_STYLES[line.tone]}>
                            {line.who}
                        </span>
                        <span className="text-gray-500">: </span>
                        <span className="text-gray-700">{line.text}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}
