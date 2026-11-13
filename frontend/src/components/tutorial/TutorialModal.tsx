import { useEffect, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import {
    ChainIllustration,
    ConnectionsIllustration,
    RunIllustration,
    SidebarIllustration,
    StepsIllustration,
    TriggerIllustration,
} from "./Illustrations";

interface Slide {
    title: string;
    image: (animate: boolean) => ReactNode;
    body: ReactNode;
}

const SLIDES: Slide[] = [
    {
        title: "Что такое сценарий",
        image: (a) => <ChainIllustration animate={a} />,
        body: (
            <>
                <p>
                    <b>Сценарий</b> — это цепочка шагов, которая выполняется сама. Например: клиент пишет на почту → «Нейросеть» готовит ответ → письмо с ответом
                    отправляется клиенту.
                </p>
                <p>Вы собираете цепочку из готовых шагов на рабочей области. Программировать не нужно: достаточно добавить шаги и соединить их линиями.</p>
            </>
        ),
    },
    {
        title: "С чего начинается сценарий",
        image: () => <TriggerIllustration />,
        body: (
            <>
                <p>
                    Первый шаг называется <b>запуск</b>. Он отвечает на вопрос: «Что должно произойти, чтобы сценарий начал работу?»
                </p>
                <p>
                    Выберите вкладку <b>«Запуск»</b> над рабочей областью: сообщение в Telegram, новое письмо, вызов по ссылке, расписание или ручной запуск по
                    кнопке. Для первой проверки удобнее всего «Ручной запуск».
                </p>
            </>
        ),
    },
    {
        title: "Шаги: что делает сценарий",
        image: (a) => <StepsIllustration animate={a} />,
        body: (
            <>
                <p>
                    Следующие шаги выполняют работу: <b>«Обработка текста»</b> находит в сообщении номер заказа или телефон, <b>«Выбор варианта»</b> направляет
                    сценарий по разным веткам, а <b>«Нейросеть»</b> пишет текст по Вашему заданию.
                </p>
                <p>
                    Чтобы добавить шаг, нажмите на него во вкладках сверху. Наведите курсор на кнопку — появится подсказка с описанием и примером. Шаги
                    соединяются линиями: потяните от точки справа у одного шага к точке слева у другого.
                </p>
            </>
        ),
    },
    {
        title: "Подключения к сервисам",
        image: (a) => <ConnectionsIllustration animate={a} />,
        body: (
            <>
                <p>
                    Чтобы сценарий мог принимать/отправлять сообщения в telegram, письма на почту или заполнять таблицу, сервис нужно подключить — в разделе «Подключения» боковой панели слева.
                </p>
                <p>
                    После этого подключение можно выбирать в нужных шагах. В Google, Яндекс и другие сервисы можно войти как с логином и паролем, так и через страницу авторизации сервиса.
                </p>
            </>
        ),
    },
    {
        title: "Проверка и включение",
        image: (a) => <RunIllustration animate={a} />,
        body: (
            <>
                <p>
                    Кнопка <b>«Запустить»</b> выполняет сценарий один раз, чтобы Вы увидели результат каждого шага. Кнопка <b>«Сохранить»</b>{" "}
                    сохраняет изменения. Подробности запусков смотрите в <b>«Журнале»</b>.
                </p>
                <p>
                    Если сценарий начинается с Telegram, письма, ссылки или расписания, нажмите <b>«Включить»</b>: после этого он работает постоянно и
                    реагирует на новые события.
                </p>
            </>
        ),
    },
    {
        title: "Обучение всегда под рукой",
        image: () => <SidebarIllustration />,
        body: (
            <>
                <p>
                    Вернуться к этой инструкции можно в любой момент: нажмите кнопку <b>«Обучение»</b> в боковой панели слева.
                </p>
                <p>Там же есть кнопка, которая откроет новый сценарий с пошаговой интерактивной подсказкой — можно собрать первую цепочку с ней вместе.</p>
            </>
        ),
    },
];

interface Props {
    open: boolean;
    onClose: () => void;
    /** welcome — первое открытие: предложение пройти интерактивное обучение; tour — обычный тур по кнопке в боковой панели */
    mode: "tour" | "welcome";
    onStartInteractive: () => void;
}

export default function TutorialModal({ open, onClose, mode, onStartInteractive }: Props) {
    const [index, setIndex] = useState(0);
    const [skipped, setSkipped] = useState(false);
    const [seen, setSeen] = useState<Record<string, boolean>>({}); // слайды, где анимация уже показана: повторно не мигают

    useEffect(() => {
        if (open) {
            setIndex(0);
            setSkipped(false);
            setSeen({});
        }
    }, [open, mode]);

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
            if (mode === "tour" && e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, SLIDES.length - 1));
            if (mode === "tour" && e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
        };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    }, [open, mode, onClose]);

    useEffect(() => {
        if (!open) return;
        const timer = window.setTimeout(() => setSeen((cur) => (cur[slideKey] ? cur : { ...cur, [slideKey]: true })), 2500);
        return () => window.clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, index, skipped, mode]);

    if (!open) return null;

    const isWelcome = mode === "welcome";
    let slide: Slide;
    if (isWelcome && !skipped) {
        slide = {
            title: "Добро пожаловать в FlowMind",
            image: (a) => <ChainIllustration animate={a} />,
            body: (
                <>
                    <p>
                        Здесь Вы собираете автоматизации из готовых шагов: бот отвечает клиентам, письма и заявки попадают в таблицу, а рутина выполняется
                        сама.
                    </p>
                    <p>Предлагаем собрать первый сценарий вместе с интерактивными подсказками. Это займёт около пяти минут.</p>
                </>
            ),
        };
    } else if (isWelcome && skipped) {
        slide = SLIDES[SLIDES.length - 1];
    } else {
        slide = SLIDES[index];
    }

    const last = index === SLIDES.length - 1;
    const slideKey = isWelcome ? `w${skipped}` : `s${index}`;
    const animate = !seen[slideKey];

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label="Обучение">
            <div className="relative flex max-h-[94vh] w-full max-w-xl flex-col overflow-y-auto rounded-xl bg-white p-6 shadow-2xl">
                <div key={`${mode}-${skipped}-${index}`} className="animate-[slideIn_0.25s_ease-out]">
                    <div className="relative">
                        {slide.image(animate)}
                        <button
                            onClick={onClose}
                            aria-label="Закрыть обучение"
                            title="Закрыть"
                            className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-500 shadow-sm hover:bg-gray-50 hover:text-gray-700"
                        >
                            <X className="h-4 w-4" />
                        </button>
                    </div>
                    <h2 className="mt-4 text-lg font-semibold text-gray-900">{slide.title}</h2>
                    <div className="mt-2 space-y-2 text-sm leading-relaxed text-gray-600">{slide.body}</div>
                </div>

                {isWelcome ? (
                    <div className="mt-6 flex items-center justify-end gap-2">
                        {!skipped ? (
                            <>
                                <button onClick={() => setSkipped(true)} className="rounded-lg px-4 py-2 text-sm text-gray-500 hover:bg-gray-100">
                                    Пропустить
                                </button>
                                <button onClick={onStartInteractive} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                                    Пройти обучение
                                </button>
                            </>
                        ) : (
                            <button onClick={onClose} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                                Понятно
                            </button>
                        )}
                    </div>
                ) : (
                    <div className="mt-6 flex items-center justify-between">
                        <button
                            onClick={() => setIndex((i) => Math.max(i - 1, 0))}
                            disabled={index === 0}
                            className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 disabled:invisible"
                        >
                            <ChevronLeft className="h-4 w-4" /> Назад
                        </button>

                        <div className="flex items-center gap-2" role="tablist" aria-label="Слайды обучения">
                            {SLIDES.map((_, i) => (
                                <button
                                    key={i}
                                    onClick={() => setIndex(i)}
                                    role="tab"
                                    aria-selected={i === index}
                                    aria-label={`Слайд ${i + 1} из ${SLIDES.length}`}
                                    className={`h-2.5 rounded-full transition-all ${i === index ? "w-6 bg-blue-600" : "w-2.5 bg-gray-300 hover:bg-gray-400"}`}
                                />
                            ))}
                        </div>

                        {last ? (
                            <div className="flex items-center gap-2">
                                <button onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-gray-500 hover:bg-gray-100">
                                    Завершить обучение
                                </button>
                                <button onClick={onStartInteractive} className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700">
                                    Попробовать
                                </button>
                            </div>
                        ) : (
                            <button
                                onClick={() => setIndex((i) => Math.min(i + 1, SLIDES.length - 1))}
                                className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50"
                            >
                                Далее <ChevronRight className="h-4 w-4" />
                            </button>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
