/** Иллюстрации обучения собраны из тех же элементов, что и сам редактор: те же иконки, цвета и подписи. */
import type { ReactElement } from "react";
import {
    Check,
    GraduationCap,
    CreditCard,
    Info,
    LogOut,
    Play,
    Save,
    Settings,
    Terminal,
    UserCircle,
} from "lucide-react";
import { NODE_META } from "../canvas/CanvasNode";
import { NODE_INFO, PALETTE_TABS } from "../../utils/glossary";

const FRAME =
    "w-full rounded-lg border border-gray-200 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:14px_14px] bg-gray-50";
const STEP = 0.28; // пауза между элементами цепочки, с: быстро, но по очереди

interface Item {
    type: string;
    /** вторая строка, как на карточке в редакторе; без неё остаются только логотип и название */
    text?: string;
    done?: string;
}

function Card({
    item,
    index,
    animate,
    hideLeft,
    hideRight,
}: {
    item: Item;
    index: number;
    animate: boolean;
    hideLeft?: boolean;
    hideRight?: boolean;
}) {
    const meta = NODE_META[item.type];
    const Icon = meta.icon;
    return (
        <div
            className={`relative shrink-0 rounded-xl border-2 bg-white shadow-sm ${meta.ring} ${item.text ? "w-[150px]" : "w-auto"}`}
            style={
                animate
                    ? {
                          opacity: 0,
                          animation: `seqIn 0.25s ease-out ${index * STEP}s forwards`,
                      }
                    : undefined
            }
        >
            {item.done && (
                <span className="absolute -top-2.5 right-2 z-10 flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-medium text-green-700 shadow">
                    <Check className="h-3 w-3" /> {item.done}
                </span>
            )}
            {!hideLeft && (
                <span className="absolute -left-1 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-gray-400" />
            )}
            {!hideRight && (
                <span className="absolute -right-1 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-gray-400" />
            )}
            <div
                className={`flex items-center gap-2 px-3 py-2 min-w-0 ${item.text ? "border-b border-gray-100" : ""}`}
            >
                <span
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${meta.badge}`}
                >
                    <Icon className="h-4 w-4" />
                </span>
                <span
                    className="truncate text-[13px] font-semibold text-gray-800"
                    title={meta.label}
                >
                    {meta.label}
                </span>
            </div>
            {item.text && (
                <div
                    className="truncate px-3 py-2 font-mono text-[11px] text-gray-500"
                    title={item.text}
                >
                    {item.text}
                </div>
            )}
        </div>
    );
}

function Line({ index, animate }: { index: number; animate: boolean }) {
    return (
        <span
            className="h-0.5 min-w-[18px] flex-1 origin-left rounded bg-blue-400"
            style={
                animate
                    ? {
                          opacity: 0,
                          animation: `lineGrow 0.2s ease-out ${index * STEP}s forwards`,
                      }
                    : undefined
            }
        />
    );
}

/** Цепочка: карточка → линия → карточка → линия → карточка. Появляется по очереди один раз и остаётся. */
function Sequence({
    items,
    animate,
    className = "",
    hideEnds = false,
}: {
    items: Item[];
    animate: boolean;
    className?: string;
    hideEnds?: boolean;
}) {
    const parts: ReactElement[] = [];
    items.forEach((item, i) => {
        parts.push(
            <Card
                key={`n${i}`}
                item={item}
                index={i * 2}
                animate={animate}
                hideLeft={hideEnds && i === 0}
                hideRight={hideEnds && i === items.length - 1}
            />,
        );
        if (i < items.length - 1)
            parts.push(
                <Line key={`l${i}`} index={i * 2 + 1} animate={animate} />,
            );
    });
    return (
        <div
            className={`flex items-center justify-center px-6 py-8 ${FRAME} ${className}`}
        >
            {parts}
        </div>
    );
}

/** Слайд 1: только логотип и название шага. */
export function ChainIllustration({ animate = true }: { animate?: boolean }) {
    return (
        <Sequence
            animate={animate}
            hideEnds
            items={[
                { type: "email_trigger" },
                { type: "llm" },
                { type: "email_send" },
            ]}
        />
    );
}

/** Слайд 3: шаги в том же порядке, что и в тексте. */
export function StepsIllustration({ animate = true }: { animate?: boolean }) {
    return (
        <Sequence
            animate={animate}
            hideEnds
            items={[
                { type: "text_transform", text: "найти номер заказа" },
                { type: "switch", text: "выбор ветки" },
                { type: "llm", text: "Напишите ответ клиенту" },
            ]}
        />
    );
}

/** Слайд 2: панель инструментов, вкладка «Запуск», как в редакторе. */
export function TriggerIllustration() {
    const tabs = ["triggers", "ai", "logic", "apps"];
    const items = [
        "manual",
        "telegram_trigger",
        "email_trigger",
        "webhook",
        "schedule",
    ];
    return (
        <div
            className="w-full select-none overflow-hidden rounded-lg border border-gray-200 bg-white"
            aria-label="Панель инструментов, вкладка «Запуск»"
            role="img"
        >
            <div className="flex items-end gap-1 bg-gray-100 px-4 pt-1">
                {tabs.map((id, i) => (
                    <span
                        key={id}
                        className={`whitespace-nowrap rounded-t-md border border-b-0 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide ${
                            i === 0
                                ? "-mb-px border-gray-200 bg-gray-50 text-blue-600"
                                : "border-transparent text-gray-500"
                        }`}
                    >
                        {PALETTE_TABS[id].label}
                    </span>
                ))}
            </div>
            <div className="flex items-start gap-1 bg-gray-50 px-4 py-1">
                {items.map((type) => {
                    const meta = NODE_META[type];
                    const Icon = meta.icon;
                    return (
                        <div
                            key={type}
                            className="flex w-[92px] shrink-0 flex-col items-center gap-1 py-1"
                        >
                            <span
                                className={`flex h-8 w-8 items-center justify-center rounded-lg ${meta.badge}`}
                            >
                                <Icon className="h-5 w-5" />
                            </span>
                            <span className="text-center text-[11px] leading-tight text-gray-700">
                                {NODE_INFO[type].label}
                            </span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

/** Слайд 4: карточка ТГ-бота как в подключениях → стрелка → нода «Сообщение в Telegram». */
export function ConnectionsIllustration({
    animate = true,
}: {
    animate?: boolean;
}) {
    const meta = NODE_META["telegram_trigger"];
    const Icon = meta.icon;
    return (
        <div
            className={`flex items-center justify-center gap-4 px-6 py-8 ${FRAME}`}
        >
            <div
                className="w-[220px] rounded-xl border border-gray-200 bg-white p-3 shadow-sm"
                style={
                    animate
                        ? {
                              opacity: 0,
                              animation: `seqIn 0.25s ease-out 0s forwards`,
                          }
                        : undefined
                }
            >
                <div className="flex items-start justify-between gap-2">
                    <div>
                        <p className="text-sm font-semibold text-gray-900">
                            FlowMindAI_bot
                        </p>
                        <p className="text-[11px] text-gray-500">
                            Telegram-бот (канал или чат)
                        </p>
                    </div>
                </div>
                <p className="mt-2 text-[11px] text-gray-600">
                    Аккаунт: @FlowMind_AI_bot
                </p>
                <p className="text-[11px] text-gray-600">
                    bot_token: ••••••HsKA
                </p>
                <p className="mt-1.5 text-[10px] text-gray-400">
                    Используется для: прослушка ТГ · ответ на сообщение
                </p>
            </div>
            <span
                className="text-2xl text-blue-500"
                style={
                    animate
                        ? {
                              opacity: 0,
                              animation: `seqIn 0.25s ease-out 0.2s forwards`,
                          }
                        : undefined
                }
            >
                →
            </span>
            <div
                className={`relative shrink-0 rounded-xl border-2 bg-white shadow-sm ${meta.ring} w-[150px]`}
                style={
                    animate
                        ? {
                              opacity: 0,
                              animation: `seqIn 0.25s ease-out 0.35s forwards`,
                          }
                        : undefined
                }
            >
                <div className="flex items-center gap-2 px-3 py-2">
                    <span
                        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${meta.badge}`}
                    >
                        <Icon className="h-4 w-4" />
                    </span>
                    <span className="truncate text-[13px] font-semibold text-gray-800">
                        {meta.label}
                    </span>
                </div>
            </div>
        </div>
    );
}

/** Слайд 5: шапка редактора с настоящими кнопками и запущенная цепочка. */
export function RunIllustration({ animate = true }: { animate?: boolean }) {
    return (
        <div
            className="w-full overflow-hidden rounded-lg border border-gray-200 bg-white"
            role="img"
            aria-label="Кнопки «Запустить» и «Сохранить»"
        >
            <div className="flex items-center justify-between gap-2 border-b border-gray-200 px-3 py-2">
                <span className="text-sm font-semibold text-gray-800">
                    Мой сценарий
                </span>
                <div className="flex shrink-0 items-center gap-1.5">
                    <span className="flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600">
                        <Terminal className="h-3.5 w-3.5" /> Журнал
                    </span>
                    <span className="flex items-center gap-1.5 whitespace-nowrap rounded-lg bg-green-600 px-3 py-1 text-xs font-medium text-white">
                        <Play className="h-3.5 w-3.5" /> Запустить
                    </span>
                    <span className="flex items-center gap-1.5 whitespace-nowrap rounded-lg bg-blue-600 px-3 py-1 text-xs font-medium text-white">
                        <Save className="h-3.5 w-3.5" /> Сохранить
                    </span>
                </div>
            </div>
            <Sequence
                animate={animate}
                hideEnds
                className="rounded-none border-0"
                items={[
                    {
                        type: "manual",
                        text: "Новое письмо клиента",
                        done: "0,1 с",
                    },
                    {
                        type: "llm",
                        text: "Напишите ответ клиенту",
                        done: "1,4 с",
                    },
                ]}
            />
        </div>
    );
}

/** Слайд 6: нижняя часть боковой панели с выделенной кнопкой «Обучение», как на сайте. */
export function SidebarIllustration() {
    const rest = [CreditCard, Info, UserCircle, Settings, LogOut];
    return (
        <div
            className={`flex items-start gap-4 px-4 pt-6 pb-8 ${FRAME}`}
            role="img"
            aria-label="Кнопка «Обучение» в боковой панели слева"
        >
            <div className="flex w-11 shrink-0 flex-col items-center gap-4 rounded-t-lg border border-b-0 border-gray-200 bg-white py-3">
                <span className="rounded-lg bg-blue-50 p-1.5 text-blue-600 ring-2 ring-blue-300">
                    <GraduationCap className="h-[18px] w-[18px]" />
                </span>
                {rest.map((Icon, i) => (
                    <span key={i} className="p-1.5 text-gray-400">
                        <Icon className="h-[18px] w-[18px]" />
                    </span>
                ))}
            </div>
            <div
                className="mt-[18px] flex items-center gap-2"
                style={{ animation: "arrowBounce 1.2s ease-in-out infinite" }}
            >
                <svg
                    width="64"
                    height="12"
                    viewBox="0 0 64 12"
                    fill="none"
                    aria-hidden
                >
                    <path
                        d="M63 6H3M8 1.5L2.5 6L8 10.5"
                        stroke="#2563eb"
                        strokeWidth="1.4"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    />
                </svg>
                <span className="whitespace-nowrap text-sm font-semibold text-blue-600">
                    Кнопка «Обучение»
                </span>
            </div>
        </div>
    );
}
