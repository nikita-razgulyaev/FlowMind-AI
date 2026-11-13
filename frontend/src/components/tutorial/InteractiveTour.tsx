import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, X } from "lucide-react";

export interface TourProgress {
    nodes: { id: string; type: string; prompt?: string }[];
    edgesCount: number;
    selectedType: string | null;
    hasRun: boolean;
    saved: boolean;
}

interface Step {
    id: string;
    target: string; // значение data-tour у подсвечиваемого элемента
    title: string;
    text: string;
    done: (p: TourProgress) => boolean;
}

export const TOUR_ACTIVE_KEY = "flowmind.tour.active";
const STEP_KEY = "flowmind.tour.step";

const TRIGGERS = ["manual", "telegram_trigger", "email_trigger", "webhook", "schedule"];

const STEPS: Step[] = [
    {
        id: "trigger",
        target: "palette",
        title: "Выберите, с чего начнётся сценарий",
        text: "Во вкладке «Запуск» нажмите «Ручной запуск»: так проще всего проверить сценарий. Позже можно выбрать Telegram или письмо.",
        done: (p) => p.nodes.some((n) => TRIGGERS.includes(n.type)),
    },
    {
        id: "llm",
        target: "palette",
        title: "Добавьте нейросеть",
        text: "Откройте вкладку «Нейросеть» и нажмите «Нейросеть». Этот шаг напишет текст по Вашему заданию.",
        done: (p) => p.nodes.some((n) => n.type === "llm"),
    },
    {
        id: "connect",
        target: "canvas",
        title: "Соедините шаги",
        text: "Потяните от точки справа у первого шага к точке слева у второго. Линия задаёт порядок выполнения.",
        done: (p) => p.edgesCount >= 1,
    },
    {
        id: "configure",
        target: "canvas",
        title: "Настройте шаг",
        text: "Нажмите на карточку «Нейросеть» — справа откроются настройки. В поле запроса напишите задание точно так: «Напишите вежливый ответ клиенту: {input}».",
        // Нужны: связь, выбранная нейросеть и точный текст запроса из подсказки
        done: (p) => {
            if (p.edgesCount < 1 || p.selectedType !== "llm") return false;
            const llm = p.nodes.find((n) => n.type === "llm");
            const expected = "Напишите вежливый ответ клиенту: {input}";
            return (llm?.prompt ?? "").trim() === expected;
        },
    },
    {
        id: "save",
        target: "save",
        title: "Сохраните сценарий",
        text: "Нажмите «Сохранить». Пока сценарий не сохранён, его нельзя запустить.",
        done: (p) => p.saved,
    },
    {
        id: "run",
        target: "run",
        title: "Проверьте работу",
        text: "Нажмите «Запустить». Сценарий выполнится один раз, а результат каждого шага появится на карточках и в «Журнале». Для работы нейросети нужно подключение в разделе «Подключения».",
        done: (p) => p.hasRun,
    },
];

function useTargetRect(target: string) {
    const [rect, setRect] = useState<DOMRect | null>(null);
    useEffect(() => {
        const update = () => {
            const el = document.querySelector(`[data-tour="${target}"]`);
            setRect(el ? el.getBoundingClientRect() : null);
        };
        update();
        const timer = window.setInterval(update, 400);
        window.addEventListener("resize", update);
        return () => {
            window.clearInterval(timer);
            window.removeEventListener("resize", update);
        };
    }, [target]);
    return rect;
}

/** Пошаговая подсказка поверх редактора: подсвечивает нужную область и сама переходит дальше, когда шаг выполнен. */
export default function InteractiveTour({
    progress,
    onClose,
    onAdvance,
}: {
    progress: TourProgress;
    onClose: () => void;
    /** Перед переходом: from — завершённый шаг, to — следующий (или "" в конце). */
    onAdvance?: (fromStepId: string, toStepId: string) => void;
}) {
    // Шаг запоминается: после первого сохранения редактор может перерисоваться, а обучение должно продолжиться с того же места
    const [index, setIndexState] = useState(() => Number(sessionStorage.getItem(STEP_KEY)) || 0);
    const setIndex = (update: number | ((i: number) => number)) =>
        setIndexState((i) => {
            const next = typeof update === "function" ? update(i) : update;
            sessionStorage.setItem(STEP_KEY, String(next));
            return next;
        });
    const finished = index >= STEPS.length;
    const step = STEPS[Math.min(index, STEPS.length - 1)];
    const stepDone = useMemo(() => !finished && step.done(progress), [finished, step, progress]);
    const rect = useTargetRect(finished ? "" : step.target);

    // Зависим и от step.id: если следующий шаг уже выполнен, stepDone остаётся true —
    // без смены step эффект бы не сработал повторно.
    useEffect(() => {
        if (!stepDone) return;
        const fromId = step.id;
        const timer = window.setTimeout(() => {
            const nextIndex = index + 1;
            const toId = nextIndex < STEPS.length ? STEPS[nextIndex].id : "";
            onAdvance?.(fromId, toId);
            setIndex(nextIndex);
        }, 900);
        return () => window.clearTimeout(timer);
    }, [stepDone, step.id]);

    return (
        <>
            {!finished && rect && (
                <div
                    aria-hidden
                    className="pointer-events-none fixed z-[55] rounded-lg"
                    style={{
                        left: rect.left - 4,
                        top: rect.top - 4,
                        width: rect.width + 8,
                        height: rect.height + 8,
                        animation: "tourPulse 1.6s ease-in-out infinite",
                        border: "2px solid #2563eb",
                    }}
                />
            )}

            <div className="fixed bottom-6 left-1/2 z-[56] w-[min(92vw,30rem)] -translate-x-1/2 rounded-xl border border-gray-200 bg-white p-4 shadow-2xl" role="status" aria-live="polite">
                <button onClick={onClose} aria-label="Закрыть обучение" className="absolute right-2 top-2 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
                    <X className="h-4 w-4" />
                </button>

                {finished ? (
                    <>
                        <p className="flex items-center gap-2 text-sm font-semibold text-gray-900">
                            <CheckCircle2 className="h-5 w-5 text-green-600" /> Готово — первый сценарий собран
                        </p>
                        <p className="mt-1 text-sm leading-snug text-gray-600">
                            Нажмите «Сохранить», чтобы он не потерялся. Чтобы бот работал постоянно, начните сценарий с Telegram или письма и нажмите «Включить».
                            Эту инструкцию можно открыть снова кнопкой «Обучение» в боковой панели слева.
                        </p>
                        <div className="mt-3 flex justify-end">
                            <button onClick={onClose} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                                Закончить
                            </button>
                        </div>
                    </>
                ) : (
                    <>
                        <p className="text-xs font-medium uppercase tracking-wide text-blue-600">
                            Шаг {index + 1} из {STEPS.length}
                        </p>
                        <p className="mt-0.5 text-sm font-semibold text-gray-900">{step.title}</p>
                        <p className="mt-1 text-sm leading-snug text-gray-600">{step.text}</p>
                        <div className="mt-3 flex items-center justify-between">
                            <button onClick={onClose} className="text-xs text-gray-400 hover:text-gray-600 hover:underline">
                                Завершить обучение
                            </button>
                            {stepDone ? (
                                <span className="flex items-center gap-1 text-sm font-medium text-green-600">
                                    <CheckCircle2 className="h-4 w-4" /> Отлично!
                                </span>
                            ) : (
                                <button onClick={() => setIndex((i) => i + 1)} className="rounded-lg px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50">
                                    Пропустить шаг
                                </button>
                            )}
                        </div>
                    </>
                )}
            </div>
        </>
    );
}
