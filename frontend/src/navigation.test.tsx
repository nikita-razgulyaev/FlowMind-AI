// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import "./i18n";
import { setAccessToken } from "./api/client";
import { useAuth } from "./store/auth";

const CONFIG = {
    deployment_mode: "cloud", auth_required: true, payment_provider: "mock", demo_mode: false,
    require_email_verification: false, default_llm_mode: "cloud", ollama_model: "qwen2.5",
    platform_ai_available: true, telegram_mode: "webhook", languages: ["ru"],
};
const LIMITS = { ai_workflows: 5, regular_workflows: 20, ai_run: 300, regular_run: 3000, telegram_triggers: 1, history_days: 14, ai_chat: 100 };
const plan = (code: string, name: string, month: number, year: number) => ({
    code, name, description: `${name} — описание`, currency: "RUB", price_month: month, price_year: year,
    features: [`Возможность тарифа ${name}`], sort_order: 0, is_public: true, limits: LIMITS,
});
const PLANS = [plan("free", "Бесплатно", 0, 0), plan("pro", "Про", 99000, 950400), plan("business", "Бизнес", 299000, 2870400)];
const ME = {
    user: { id: 1, email: "me@example.com", name: "Я", role: "user", email_verified: true, is_local: false, created_at: "2026-01-01T00:00:00Z" },
    plan: PLANS[0],
    subscription: { plan_code: "free", effective_plan: "free", period: null, status: "active", current_period_start: null, current_period_end: null,
        cancel_at_period_end: false, pending_plan_code: null, pending_period: null, payment_method_label: null, provider: null, amount_paid: 0 },
    usage: { ai_run: 0, regular_run: 0, ai_chat: 0 },
    workflows: { ai_workflows: 0, regular_workflows: 0, telegram_triggers: 0 },
};

function mockApi(loggedIn: boolean) {
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/config")) return json(CONFIG);
        if (url.endsWith("/api/auth/refresh")) return loggedIn ? json({ access_token: "tok", user: ME.user }) : json({ detail: { message: "no session" } }, 401);
        if (url.endsWith("/api/me")) return json(ME);
        if (url.endsWith("/api/me/settings")) return json({});
        if (url.endsWith("/api/plans")) return json(PLANS);
        return json([]);
    }) as typeof fetch;
}

async function openApp(path: string, loggedIn: boolean) {
    mockApi(loggedIn);
    render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
    await waitFor(() => expect(useAuth.getState().ready).toBe(true));
}

const header = () => within(screen.getByRole("banner"));

beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    window.scrollTo = vi.fn() as typeof window.scrollTo;
    setAccessToken(null);
    useAuth.setState({ ready: false, config: null, me: null });
});
afterEach(() => cleanup());

describe("навигация для гостя", () => {
    it("лендинг → тарифы → якорь «Возможности» → вход → логотип", async () => {
        const user = userEvent.setup();
        await openApp("/", false);
        expect(await screen.findByRole("heading", { level: 1, name: /Собирайте AI-автоматизации/ })).toBeTruthy();

        await user.click(header().getByRole("link", { name: "Тарифы" }));
        expect(await screen.findByRole("heading", { level: 1, name: "Тарифы" })).toBeTruthy();
        expect(await screen.findByText("Возможность тарифа Про")).toBeTruthy();
        expect(screen.queryByText("Сравнение тарифов")).toBeNull();                    // таблицы сравнения больше нет
        expect(header().getByRole("link", { name: "Тарифы" }).getAttribute("aria-current")).toBe("page");

        await user.click(header().getByRole("link", { name: "Возможности" }));           // с /pricing на якорь лендинга
        expect(await screen.findByRole("heading", { level: 1, name: /Собирайте AI-автоматизации/ })).toBeTruthy();
        await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
        const scrolledTo = (Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mock.contexts.at(-1) as HTMLElement;
        expect(scrolledTo.id).toBe("features");

        await user.click(header().getByRole("link", { name: "Войти" }));
        expect(await screen.findByRole("heading", { name: "Вход в FlowMind AI" })).toBeTruthy();

        await user.click(screen.getByRole("link", { name: /FlowMind AI/ }));              // логотип возвращает на главную
        expect(await screen.findByRole("heading", { level: 1, name: /Собирайте AI-автоматизации/ })).toBeTruthy();
    });

    it("выбор платного тарифа ведёт на регистрацию, а закрытые страницы — на вход", async () => {
        const user = userEvent.setup();
        await openApp("/pricing", false);
        await user.click(await screen.findByRole("button", { name: "Выбрать «Про»" }));
        expect(await screen.findByRole("heading", { name: "Создать аккаунт" })).toBeTruthy();

        cleanup();
        useAuth.setState({ ready: false, config: null, me: null });
        await openApp("/workflow/new", false);
        expect(await screen.findByRole("heading", { name: "Вход в FlowMind AI" })).toBeTruthy();
    });
});

describe("навигация для вошедшего", () => {
    it("приложение ↔ тарифы ↔ презентация", async () => {
        const user = userEvent.setup();
        await openApp("/", true);
        expect(await screen.findByTitle("Воркфлоу")).toBeTruthy();                        // это приложение (боковая панель), а не лендинг
        expect(screen.queryByRole("heading", { name: /Собирайте AI-автоматизации/ })).toBeNull();

        await user.click(screen.getByTitle("Тарифы"));
        expect(await screen.findByRole("heading", { level: 1, name: "Тарифы" })).toBeTruthy();
        expect(await screen.findByText("Текущий тариф")).toBeTruthy();                    // у вошедшего отмечен его тариф

        await user.click(header().getByRole("link", { name: "Личный кабинет" }));
        expect(await screen.findByRole("heading", { name: "Личный кабинет" })).toBeTruthy();

        await user.click(screen.getByTitle("О сервисе"));
        expect(await screen.findByRole("heading", { level: 1, name: /Собирайте AI-автоматизации/ })).toBeTruthy();
        await user.click(header().getByRole("link", { name: "Открыть приложение" }));
        expect(await screen.findByTitle("Воркфлоу")).toBeTruthy();
    });

    it("вошедшего не пускают на страницы входа и регистрации", async () => {
        await openApp("/login", true);
        expect(await screen.findByTitle("Воркфлоу")).toBeTruthy();
    });
});
