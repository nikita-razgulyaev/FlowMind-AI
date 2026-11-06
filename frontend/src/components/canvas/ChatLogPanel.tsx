import { useEffect, useRef, useState } from "react";
import { CheckCircle2, ChevronDown, Loader2, Trash2, X, XCircle } from "lucide-react";
import {
    buildLines,
    extractTriggerInput,
    formatDate,
    splitBold,
    type ExecutionRecord,
} from "../../utils/executionLog";

interface Props {
    executions: ExecutionRecord[];       // новые сверху
    focusId?: number | null;             // запуск, который нужно раскрыть и показать
    onClear: () => void;
    onClose: () => void;
}

const MAX_SHOWN = 30;

const TONE_STYLES: Record<string, string> = {
    user: "text-gray-500",
    agent: "text-indigo-700 font-medium",
    tool: "text-emerald-700 font-medium",
    muted: "text-gray-400",
};

const STATUS_ICON: Record<string, { icon: typeof CheckCircle2; color: string }> = {
    success: { icon: CheckCircle2, color: "text-emerald-600" },
    failed: { icon: XCircle, color: "text-red-600" },
    cancelled: { icon: XCircle, color: "text-gray-500" },
    running: { icon: Loader2, color: "text-blue-600 animate-spin" },
};

export default function ChatLogPanel({ executions, focusId, onClear, onClose }: Props) {
    const [openId, setOpenId] = useState<number | null>(null);
    const focusRef = useRef<HTMLDivElement>(null);

    // раскрываем запрошенный запуск, иначе самый свежий
    useEffect(() => {
        setOpenId(focusId ?? executions[0]?.id ?? null);
    }, [focusId, executions[0]?.id]);

    useEffect(() => {
        if (focusId && openId === focusId) focusRef.current?.scrollIntoView({ block: "nearest" });
    }, [focusId, openId, executions.length]);

    return (
        <div className="border-t border-gray-200 bg-white max-h-72 overflow-y-auto">
            <div className="flex items-center justify-between px-4 py-2 sticky top-0 z-10 bg-white border-b border-gray-100">
                <span className="text-xs font-semibold text-gray-500">
                    Чат-лог выполнения
                    {executions.length > 0 && (
                        <span className="ml-2 font-normal text-gray-400">запусков: {executions.length}</span>
                    )}
                </span>
                <div className="flex items-center gap-1">
                    {executions.length > 0 && (
                        <button
                            onClick={onClear}
                            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-red-600 hover:bg-red-50 rounded"
                            title="Удалить эти запуски из истории выполнений"
                        >
                            <Trash2 className="w-3.5 h-3.5" /> Очистить логи
                        </button>
                    )}
                    <button
                        onClick={onClose}
                        className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {executions.length === 0 && (
                <p className="px-4 py-3 text-xs text-gray-400">
                    Пока нет данных — запусти workflow (Run).
                </p>
            )}

            {executions.slice(0, MAX_SHOWN).map((ex) => {
                const isOpen = openId === ex.id;
                const status = STATUS_ICON[ex.status] || STATUS_ICON.running;
                const StatusIcon = status.icon;
                const lines = isOpen ? buildLines(extractTriggerInput(ex.trigger_data), ex.logs || []) : [];
                return (
                    <div key={ex.id} ref={ex.id === focusId ? focusRef : undefined} className="border-b border-gray-100">
                        <button
                            onClick={() => setOpenId(isOpen ? null : ex.id)}
                            className="flex w-full items-center gap-2 px-4 py-1.5 text-left text-xs hover:bg-gray-50"
                        >
                            <ChevronDown
                                className={`w-3.5 h-3.5 text-gray-300 transition-transform ${isOpen ? "" : "-rotate-90"}`}
                            />
                            <StatusIcon className={`w-3.5 h-3.5 ${status.color}`} />
                            <span className="font-medium text-gray-700">#{ex.id}</span>
                            {ex.source && ex.source !== "manual" && (
                                <span className="rounded bg-gray-100 px-1.5 text-gray-500">{ex.source}</span>
                            )}
                            <span className="text-gray-400">{formatDate(ex.started_at)}</span>
                        </button>
                        {isOpen && (
                            <div className="space-y-1.5 px-4 pb-2 pl-10">
                                {lines.length === 0 && <p className="text-xs text-gray-400">Нет данных</p>}
                                {lines.map((line, i) => (
                                    <div key={i} className="text-xs">
                                        <span className={TONE_STYLES[line.tone]}>{line.who}</span>
                                        <span className="text-gray-500">: </span>
                                        <span className="whitespace-pre-wrap break-words text-gray-700">{splitBold(line.text).map((part, j) =>
                                                part.bold ? <strong key={j} className="font-semibold text-gray-900">{part.text}</strong> : part.text,
                                            )}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                );
            })}
            {executions.length > MAX_SHOWN && (
                <p className="px-4 py-2 text-xs text-gray-400">
                    Показаны {MAX_SHOWN} последних, остальные — в «Истории выполнений».
                </p>
            )}
        </div>
    );
}
