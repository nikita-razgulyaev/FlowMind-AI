import { useState } from "react";
import { Sparkles } from "lucide-react";

export default function AiChatPanel() {
    const [draft, setDraft] = useState("");

    return (
        <div className="w-64 shrink-0 bg-white border-l border-gray-200 h-full flex flex-col">
            <div className="px-4 py-3 border-b border-gray-100">
                <p className="text-sm font-semibold text-gray-800">
                    Собери граф текстом
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                    Скоро — пока не подключено к backend
                </p>
            </div>

            <div className="flex-1 px-4 py-3 space-y-2 overflow-y-auto">
                <div className="flex items-start gap-2 text-xs text-gray-500 bg-gray-50 rounded-lg p-3">
                    <Sparkles className="w-4 h-4 shrink-0 mt-0.5 text-indigo-400" />
                    <span>
                        Здесь появится ассистент, который добавляет и соединяет
                        ноды на canvas по твоему текстовому описанию — сейчас
                        это только заготовка интерфейса.
                    </span>
                </div>
            </div>

            <div className="p-3 border-t border-gray-100">
                <input
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    disabled
                    placeholder="Опиши, что добавить... (пока недоступно)"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-xs bg-gray-50 text-gray-400 cursor-not-allowed"
                />
            </div>
        </div>
    );
}
