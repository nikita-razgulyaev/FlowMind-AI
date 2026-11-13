import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { NODE_META } from "./CanvasNode";
import { NODE_INFO, PALETTE_TABS } from "../../utils/glossary";

interface PaletteGroup {
    label: string;
    items: string[];
    /** true — группа свёрнута в одну кнопку с выпадающим списком */
    dropdown?: boolean;
}

interface PaletteTab {
    id: string;
    groups: PaletteGroup[];
}

const TABS: PaletteTab[] = [
    {
        id: "triggers",
        groups: [{ label: "Запуск", items: ["manual", "telegram_trigger", "email_trigger", "webhook", "schedule"] }],
    },
    {
        id: "ai",
        groups: [{ label: "Нейросеть", items: ["llm", "agent"] }],
    },
    {
        id: "logic",
        groups: [
            { label: "Ветвление", items: ["condition", "switch"] },
            { label: "Текст и данные", items: ["text_transform", "text_input", "set"], dropdown: true },
            { label: "Результат", items: ["print"] },
        ],
    },
    {
        id: "apps",
        groups: [
            { label: "Сеть", items: ["http"] },
            { label: "Telegram", items: ["telegram_send"] },
            { label: "Почта", items: ["email_send"] },
            { label: "Таблицы", items: ["google_sheets_append"] },
            { label: "Календарь", items: ["google_calendar_create_event"] },
        ],
    },
];

/** Всплывающая подсказка с задержкой: название, что делает и пример. */
function HintBubble({ title, hint, example, children }: { title: string; hint: string; example?: string; children: ReactNode }) {
    return (
        <div className="group relative">
            {children}
            <div className="pointer-events-none absolute left-1/2 top-full z-40 mt-1 hidden w-64 max-w-[min(16rem,calc(100vw-2rem))] -translate-x-1/2 rounded-lg border border-gray-200 bg-white p-3 text-left shadow-xl group-hover:block group-hover:animate-[fadeIn_0.15s_ease-out_0.4s_both]">
                <p className="text-xs font-semibold text-gray-800">{title}</p>
                <p className="mt-1 text-xs leading-snug text-gray-600">{hint}</p>
                {example && (
                    <p className="mt-1.5 text-[11px] leading-snug text-gray-400">
                        <span className="font-medium text-gray-500">Пример: </span>
                        {example}
                    </p>
                )}
                <p className="mt-1.5 text-[11px] text-blue-600">Нажмите, чтобы добавить на рабочую область</p>
            </div>
        </div>
    );
}

function ToolButton({ type, onAdd }: { type: string; onAdd: (type: string) => void }) {
    const meta = NODE_META[type];
    const info = NODE_INFO[type];
    const Icon = meta.icon;
    return (
        <HintBubble title={info.label} hint={info.hint} example={info.example}>
            <button
                onClick={() => onAdd(type)}
                aria-label={`Добавить шаг: ${info.label}`}
                data-tour={`add-${type}`}
                className="flex flex-col items-center gap-1 w-[92px] py-1 rounded-md hover:bg-gray-200/70 active:bg-gray-300/70"
            >
                <span className={`flex items-center justify-center w-8 h-8 rounded-lg ${meta.badge}`}>
                    <Icon className="w-5 h-5" />
                </span>
                <span className="text-center text-[11px] leading-tight text-gray-700">{meta.label}</span>
            </button>
        </HintBubble>
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
                title="Нажмите, чтобы выбрать шаг из списка"
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
                <div className="absolute left-0 top-full mt-1 z-30 w-[300px] rounded-lg border border-gray-200 bg-white py-1 shadow-xl">
                    {group.items.map((type) => {
                        const meta = NODE_META[type];
                        const info = NODE_INFO[type];
                        const ItemIcon = meta.icon;
                        return (
                            <button
                                key={type}
                                onClick={() => {
                                    onAdd(type);
                                    setOpen(false);
                                }}
                                className="flex w-full items-start gap-2.5 px-3 py-2 text-left hover:bg-gray-100"
                            >
                                <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded ${meta.badge}`}>
                                    <ItemIcon className="w-4 h-4" />
                                </span>
                                <span>
                                    <span className="block text-sm text-gray-800">{meta.label}</span>
                                    <span className="block text-[11px] leading-snug text-gray-500">{info.hint}</span>
                                </span>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

/** Панель добавления шагов: вкладки сверху, группы с подписями и выпадающими списками. У каждого элемента — понятная подсказка. */
export default function NodePalette({ onAdd }: { onAdd: (type: string) => void }) {
    const [activeId, setActiveId] = useState(TABS[0].id);
    const tab = TABS.find((t) => t.id === activeId) ?? TABS[0];

    return (
        <div className="border-b border-gray-200 bg-white select-none" data-tour="palette">
            <div className="flex items-end gap-1 px-4 pt-1 bg-gray-100">
                {TABS.map((t) => (
                    <button
                        key={t.id}
                        onClick={() => setActiveId(t.id)}
                        title={PALETTE_TABS[t.id].hint}
                        className={`px-4 py-1 text-xs font-semibold uppercase tracking-wide rounded-t-md border border-b-0 ${
                            t.id === activeId
                                ? "bg-gray-50 text-blue-600 border-gray-200 -mb-px"
                                : "border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-200/60"
                        }`}
                    >
                        {PALETTE_TABS[t.id].label}
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
                    </div>
                ))}
            </div>
        </div>
    );
}
