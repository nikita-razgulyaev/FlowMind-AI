import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { NODE_META } from "./CanvasNode";

interface PaletteGroup {
    label: string;
    items: string[];
    /** true — группа свёрнута в одну кнопку с выпадающим списком */
    dropdown?: boolean;
}

interface PaletteTab {
    id: string;
    label: string;
    groups: PaletteGroup[];
}

const TABS: PaletteTab[] = [
    {
        id: "triggers",
        label: "Триггеры",
        groups: [{ label: "Запуск", items: ["manual", "telegram_trigger", "webhook", "schedule"] }],
    },
    {
        id: "ai",
        label: "AI",
        groups: [{ label: "Модели", items: ["llm", "agent"] }],
    },
    {
        id: "logic",
        label: "Логика и данные",
        groups: [
            { label: "Ветвление", items: ["condition", "switch"] },
            { label: "Данные", items: ["text_input", "set", "print"], dropdown: true },
        ],
    },
    {
        id: "apps",
        label: "Интеграции",
        groups: [
            { label: "Сеть", items: ["http"] },
            { label: "Telegram", items: ["telegram_send"] },
            { label: "Google", items: ["google_sheets_append", "google_calendar_create_event"], dropdown: true },
        ],
    },
];

function ToolButton({ type, onAdd }: { type: string; onAdd: (type: string) => void }) {
    const meta = NODE_META[type];
    const Icon = meta.icon;
    return (
        <button
            onClick={() => onAdd(type)}
            title={`Добавить: ${meta.label}`}
            className="flex flex-col items-center gap-1 w-[92px] py-1 rounded-md hover:bg-gray-200/70 active:bg-gray-300/70"
        >
            <span className={`flex items-center justify-center w-8 h-8 rounded-lg ${meta.badge}`}>
                <Icon className="w-5 h-5" />
            </span>
            <span className="whitespace-nowrap text-[11px] leading-tight text-gray-700">{meta.label}</span>
        </button>
    );
}

function DropdownGroup({ group, onAdd }: { group: PaletteGroup; onAdd: (type: string) => void }) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    const first = NODE_META[group.items[0]];
    const Icon = first.icon;

    useEffect(() => {
        if (!open) return;
        const close = (e: MouseEvent) => {
            if (!ref.current?.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener("mousedown", close);
        return () => document.removeEventListener("mousedown", close);
    }, [open]);

    return (
        <div ref={ref} className="relative">
            <button
                onClick={() => setOpen((v) => !v)}
                className={`flex flex-col items-center gap-1 w-[92px] py-1 rounded-md hover:bg-gray-200/70 ${open ? "bg-gray-200/70" : ""}`}
            >
                <span className={`flex items-center justify-center w-8 h-8 rounded-lg ${first.badge}`}>
                    <Icon className="w-5 h-5" />
                </span>
                <span className="flex items-center whitespace-nowrap text-[11px] leading-tight text-gray-700">
                    {group.label}
                    <ChevronDown className="w-3 h-3 ml-0.5" />
                </span>
            </button>
            {open && (
                <div className="absolute left-0 top-full mt-1 z-30 min-w-[210px] rounded-lg border border-gray-200 bg-white py-1 shadow-xl">
                    {group.items.map((type) => {
                        const meta = NODE_META[type];
                        const ItemIcon = meta.icon;
                        return (
                            <button
                                key={type}
                                onClick={() => {
                                    onAdd(type);
                                    setOpen(false);
                                }}
                                className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
                            >
                                <span className={`flex items-center justify-center w-6 h-6 rounded ${meta.badge}`}>
                                    <ItemIcon className="w-4 h-4" />
                                </span>
                                {meta.label}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

/** Панель добавления нод в духе ленты Fusion 360: вкладки сверху, группы с подписями и выпадающими списками. */
export default function NodePalette({ onAdd }: { onAdd: (type: string) => void }) {
    const [activeId, setActiveId] = useState(TABS[0].id);
    const tab = TABS.find((t) => t.id === activeId) ?? TABS[0];

    return (
        <div className="border-b border-gray-200 bg-white select-none">
            <div className="flex items-end gap-1 px-4 pt-1 bg-gray-100">
                {TABS.map((t) => (
                    <button
                        key={t.id}
                        onClick={() => setActiveId(t.id)}
                        className={`px-4 py-1 text-xs font-semibold uppercase tracking-wide rounded-t-md border border-b-0 ${
                            t.id === activeId
                                ? "bg-gray-50 text-blue-600 border-gray-200 -mb-px"
                                : "border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-200/60"
                        }`}
                    >
                        {t.label}
                    </button>
                ))}
            </div>
            <div className="flex items-stretch gap-0 px-4 py-1 bg-gray-50">
                {tab.groups.map((group) => (
                    <div key={group.label} className="flex flex-col justify-between px-2 border-r border-gray-200 last:border-r-0">
                        <div className="flex items-start gap-1">
                            {group.dropdown ? (
                                <DropdownGroup group={group} onAdd={onAdd} />
                            ) : (
                                group.items.map((type) => <ToolButton key={type} type={type} onAdd={onAdd} />)
                            )}
                        </div>
                        <span
                            className={`text-center text-[10px] leading-3 uppercase tracking-wider text-gray-400 ${group.dropdown ? "invisible" : ""}`}
                        >
                            {group.label}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}
