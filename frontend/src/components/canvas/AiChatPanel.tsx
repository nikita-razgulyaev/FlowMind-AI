import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, Send, Check, Loader2 } from "lucide-react";
import { api } from "../../api/client";
import type { AiChatMessage } from "../../types/app";

interface Graph {
    nodes: any[];
    edges: any[];
}

interface Props {
    getGraph: () => Graph;
    onApply: (graph: Graph) => void;
}

interface ChatItem extends AiChatMessage {
    workflow?: Graph | null;
    applied?: boolean;
}

const SUGGESTIONS = [
    "Telegram-бот поддержки: агент отвечает на вопросы клиентов",
    "По кнопке Run получить погоду по HTTP и коротко пересказать через LLM",
    "Добавь условие: если ответ длиннее 200 символов — отправить в Telegram",
];

export default function AiChatPanel({ getGraph, onApply }: Props) {
    const [items, setItems] = useState<ChatItem[]>([]);
    const [draft, setDraft] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<{ message: string; code?: string } | null>(null);
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [items, loading]);

    const send = async (text: string) => {
        const content = text.trim();
        if (!content || loading) return;
        const next: ChatItem[] = [...items, { role: "user", content }];
        setItems(next);
        setDraft("");
        setError(null);
        setLoading(true);

        const graph = getGraph();
        const { data, error: err, code } = await api.aiChat(
            next.map(({ role, content: c }) => ({ role, content: c })),
            graph.nodes.length ? graph : null,
        );
        setLoading(false);
        if (!data) {
            setError({ message: err ?? "Не удалось получить ответ", code });
            return;
        }
        setItems([...next, { role: "assistant", content: data.reply, workflow: data.workflow }]);
    };

    const apply = (index: number) => {
        const item = items[index];
        if (!item.workflow) return;
        onApply(item.workflow);
        setItems(items.map((it, i) => (i === index ? { ...it, applied: true } : it)));
    };

    return (
        <div className="w-80 shrink-0 bg-white border-l border-gray-200 h-full flex flex-col">
            <div className="px-4 py-3 border-b border-gray-100">
                <p className="text-sm font-semibold text-gray-800 flex items-center gap-1.5">
                    <Sparkles className="w-4 h-4 text-indigo-500" /> AI-чат
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                    Опиши сценарий — ассистент соберёт или изменит граф. Результат нужно применить и сохранить.
                </p>
            </div>

            <div className="flex-1 px-3 py-3 space-y-3 overflow-y-auto">
                {items.length === 0 && (
                    <div className="space-y-2">
                        <p className="text-xs text-gray-400">Например:</p>
                        {SUGGESTIONS.map((s) => (
                            <button
                                key={s}
                                onClick={() => send(s)}
                                className="block w-full text-left text-xs text-gray-600 bg-gray-50 hover:bg-indigo-50 rounded-lg p-2.5"
                            >
                                {s}
                            </button>
                        ))}
                    </div>
                )}

                {items.map((item, i) => (
                    <div key={i} className={item.role === "user" ? "flex justify-end" : "flex justify-start"}>
                        <div
                            className={`max-w-[90%] rounded-xl px-3 py-2 text-xs whitespace-pre-wrap ${
                                item.role === "user" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-800"
                            }`}
                        >
                            {item.content}
                            {item.workflow && (
                                <div className="mt-2 pt-2 border-t border-gray-200">
                                    <p className="text-[11px] text-gray-500 mb-1.5">
                                        Граф: {item.workflow.nodes.length} нод, {item.workflow.edges.length} связей
                                    </p>
                                    <button
                                        onClick={() => apply(i)}
                                        disabled={item.applied}
                                        className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-indigo-600 text-white text-[11px] font-medium hover:bg-indigo-700 disabled:bg-emerald-600"
                                    >
                                        {item.applied ? (
                                            <>
                                                <Check className="w-3 h-3" /> Применено
                                            </>
                                        ) : (
                                            "Применить к холсту"
                                        )}
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                ))}

                {loading && (
                    <div className="flex items-center gap-2 text-xs text-gray-400">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Думаю…
                    </div>
                )}
                {error && (
                    <div className="text-xs text-red-600 bg-red-50 rounded-lg p-2.5">
                        {error.message}
                        {error.code === "quota_exceeded" && (
                            <Link to="/pricing" className="block mt-1 font-medium underline">
                                Посмотреть тарифы
                            </Link>
                        )}
                    </div>
                )}
                <div ref={bottomRef} />
            </div>

            <form
                className="p-3 border-t border-gray-100 flex gap-2"
                onSubmit={(e) => {
                    e.preventDefault();
                    void send(draft);
                }}
            >
                <input
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="Опиши, что собрать или изменить…"
                    maxLength={4000}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400"
                />
                <button
                    type="submit"
                    disabled={loading || !draft.trim()}
                    className="p-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40"
                    title="Отправить"
                >
                    <Send className="w-4 h-4" />
                </button>
            </form>
        </div>
    );
}
