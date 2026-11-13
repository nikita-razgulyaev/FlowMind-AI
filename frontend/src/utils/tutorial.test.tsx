// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TutorialModal from "../components/tutorial/TutorialModal";
import InteractiveTour, { type TourProgress } from "../components/tutorial/InteractiveTour";
import { paramsToSchema, schemaToParams } from "../components/canvas/ToolSettings";
import { TEXT_OPERATIONS } from "./textOperations";
import { NODE_INFO } from "./glossary";

afterEach(() => {
    cleanup();
    sessionStorage.clear();
});

describe("обучение в окне", () => {
    it("листается кнопками «Далее»/«Назад», точки показывают текущий слайд", async () => {
        const user = userEvent.setup();
        render(<TutorialModal open mode="tour" onClose={() => {}} onStartInteractive={() => {}} />);
        expect(screen.getByText("Что такое сценарий")).toBeTruthy();
        expect(screen.getAllByRole("tab")[0].getAttribute("aria-selected")).toBe("true");
        await user.click(screen.getByText("Далее"));
        expect(screen.getByText("С чего начинается сценарий")).toBeTruthy();
        expect(screen.getAllByRole("tab")[1].getAttribute("aria-selected")).toBe("true");
        await user.click(screen.getByText("Назад"));
        expect(screen.getByText("Что такое сценарий")).toBeTruthy();
    });

    it("последний слайд говорит про кнопку в боковой панели и предлагает попробовать на практике", async () => {
        const user = userEvent.setup();
        const start = vi.fn();
        render(<TutorialModal open mode="tour" onClose={() => {}} onStartInteractive={start} />);
        const dots = screen.getAllByRole("tab");
        await user.click(dots[dots.length - 1]);
        expect(screen.getByText("Обучение всегда под рукой")).toBeTruthy();
        await user.click(screen.getByText("Попробовать"));
        expect(start).toHaveBeenCalled();
    });

    it("на последнем слайде рядом с «Попробовать» есть «Завершить обучение», оно закрывает окно", async () => {
        const user = userEvent.setup();
        const close = vi.fn();
        render(<TutorialModal open mode="tour" onClose={close} onStartInteractive={() => {}} />);
        const dots = screen.getAllByRole("tab");
        await user.click(dots[dots.length - 1]);
        await user.click(screen.getByText("Завершить обучение"));
        expect(close).toHaveBeenCalled();
    });

    it("при первом открытии: «Пропустить» меняет слайд на подсказку про боковую панель", async () => {
        const user = userEvent.setup();
        const close = vi.fn();
        render(<TutorialModal open mode="welcome" onClose={close} onStartInteractive={() => {}} />);
        expect(screen.getByText("Добро пожаловать в FlowMind")).toBeTruthy();
        await user.click(screen.getByText("Пропустить"));
        expect(screen.getByText("Обучение всегда под рукой")).toBeTruthy();
        await user.click(screen.getByText("Понятно"));
        expect(close).toHaveBeenCalled();
    });
});

describe("интерактивная подсказка", () => {
    const base: TourProgress = { nodes: [], edgesCount: 0, selectedType: null, hasRun: false, saved: false };

    it("ждёт действия пользователя и переходит дальше сама", async () => {
        vi.useFakeTimers();
        const { rerender } = render(<InteractiveTour progress={base} onClose={() => {}} />);
        expect(screen.getByText(/Шаг 1 из/)).toBeTruthy();
        rerender(<InteractiveTour progress={{ ...base, nodes: [{ id: "a", type: "manual" }] }} onClose={() => {}} />);
        expect(screen.getByText("Отлично!")).toBeTruthy();
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });
        expect(screen.getByText(/Шаг 2 из/)).toBeTruthy();
        vi.useRealTimers();
    });
});

describe("конструктор параметров инструмента", () => {
    it("собирает схему и разбирает её обратно, примеры сохраняются", () => {
        const schema = paramsToSchema([{ name: "order_id", description: "ID заказа", examples: ["1234", " ", "№1234 от 05.11.26"], required: true }]);
        expect(schema).toEqual({
            type: "object",
            properties: { order_id: { type: "string", description: "ID заказа", examples: ["1234", "№1234 от 05.11.26"] } },
            required: ["order_id"],
        });
        expect(schemaToParams(schema)?.[0]).toMatchObject({ name: "order_id", required: true, examples: ["1234", "№1234 от 05.11.26"] });
    });

    it("сложную схему (не строки) не ломает: простой вид недоступен, остаётся JSON", () => {
        expect(schemaToParams({ type: "object", properties: { n: { type: "number" } } })).toBeNull();
    });
});

describe("словарь", () => {
    it("у каждого действия обработки текста и каждого шага есть понятное описание", () => {
        expect(TEXT_OPERATIONS.every((o) => o.label && o.hint)).toBe(true);
        expect(Object.values(NODE_INFO).every((n) => n.label.length <= 24 && n.hint.length > 20)).toBe(true);
    });
});
