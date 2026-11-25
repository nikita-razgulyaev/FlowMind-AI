// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import "./i18n";
import { setAccessToken } from "./api/client";
import { useAuth } from "./store/auth";

const CONTACTS = { email: "help@flowmind.example", telegram: { label: "@flowmind_support", url: "https://t.me/flowmind_support" } };
const config = (over: Record<string, unknown> = {}) => ({
    deployment_mode: "cloud", auth_required: true, payment_provider: "mock", demo_mode: false,
    require_email_verification: false, default_llm_mode: "cloud", ollama_model: "qwen2.5",
    platform_ai_available: true, telegram_mode: "webhook", languages: ["ru"],
    feedback_enabled: true, contacts: CONTACTS, ...over,
});
const LIMITS = { ai_workflows: 5, regular_workflows: 20, ai_run: 50, regular_run: 3000, telegram_triggers: 1, history_days: 14, ai_chat: 25 };
const PLANS = [{ code: "free", name: "Бесплатно", description: "d", currency: "RUB", price_month: 0, price_year: 0, features: ["f"], sort_order: 0, is_public: true, limits: LIMITS }];

async function openLanding(path = "/about", cfg = config()) {
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/config")) return json(cfg);
        if (url.endsWith("/api/auth/refresh")) return json({ detail: { message: "no session" } }, 401);
        if (url.endsWith("/api/plans")) return json(PLANS);
        return json([]);
    }) as typeof fetch;
    render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
    await waitFor(() => expect(useAuth.getState().ready).toBe(true));
}

const header = () => within(screen.getByRole("banner"));
const lastScrollTarget = () => (Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mock.contexts.at(-1) as HTMLElement | undefined;

beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    window.scrollTo = vi.fn() as typeof window.scrollTo;
    setAccessToken(null);
    useAuth.setState({ ready: false, config: null, me: null });
});
afterEach(() => cleanup());

describe("блок «Написать нам» на лендинге", () => {
    it("отдельный блок с заголовком «Написать нам» и формой, без заголовка «Контакты» и без самих контактов", async () => {
        await openLanding();
        const section = (await screen.findByRole("heading", { level: 2, name: "Написать нам" })).closest("section") as HTMLElement;
        expect(section.id).toBe("contact");
        expect(section.className).toContain("scroll-mt-20");                           // шапка не закрывает заголовок при скролле
        expect(within(section).getByRole("textbox", { name: /Сообщение/ })).toBeTruthy();
        expect(within(section).getByRole("button", { name: "Отправить" })).toBeTruthy();

        expect(screen.queryByRole("heading", { name: "Контакты" })).toBeNull();
        expect(within(section).queryByRole("link", { name: /help@flowmind\.example/ })).toBeNull();
        expect(within(section).queryByRole("link", { name: /Telegram|@flowmind_support/ })).toBeNull();
    });

    it("кнопка «Написать нам» в навигации плавно прокручивает к блоку", async () => {
        const user = userEvent.setup();
        await openLanding();
        const link = header().getByRole("link", { name: "Написать нам" });
        expect(link.getAttribute("href")).toBe("/about#contact");
        await user.click(link);
        await waitFor(() => expect(lastScrollTarget()?.id).toBe("contact"));
    });

    it("прямая ссылка /about#contact открывает лендинг сразу у формы, а пункт навигации подсвечен", async () => {
        await openLanding("/about#contact");
        await screen.findByRole("heading", { level: 2, name: "Написать нам" });
        await waitFor(() => expect(lastScrollTarget()?.id).toBe("contact"));
        expect(header().getByRole("link", { name: "Написать нам" }).getAttribute("aria-current")).toBe("page");
    });

    it("со страницы тарифов та же кнопка ведёт на лендинг и прокручивает к форме", async () => {
        const user = userEvent.setup();
        await openLanding("/pricing");
        await user.click(header().getByRole("link", { name: "Написать нам" }));
        expect(await screen.findByRole("heading", { level: 2, name: "Написать нам" })).toBeTruthy();
        await waitFor(() => expect(lastScrollTarget()?.id).toBe("contact"));
    });

    it("в футере нет навигации, только копирайт и контакты", async () => {
        await openLanding();
        const footer = within(screen.getByRole("contentinfo"));
        for (const name of ["Возможности", "Тарифы", "Частые вопросы", "Контакты", "Написать нам", "Войти", "Регистрация"]) {
            expect(footer.queryByRole("link", { name }), name).toBeNull();
        }
        expect(footer.queryByRole("navigation")).toBeNull();
        expect(footer.getByText(/FlowMind AI/)).toBeTruthy();
        expect(footer.getByRole("link", { name: /help@flowmind\.example/ })).toBeTruthy();
        expect(footer.getByRole("link", { name: /@flowmind_support/ })).toBeTruthy();
        // навигация осталась в шапке
        expect(header().getByRole("link", { name: "Написать нам" }).getAttribute("href")).toBe("/about#contact");
    });

    it("если форма отключена, блока нет, а ссылка ведёт на страницу контактов (или исчезает, если контактов нет)", async () => {
        await openLanding("/about", config({ feedback_enabled: false }));
        expect(screen.queryByRole("heading", { level: 2, name: "Написать нам" })).toBeNull();
        expect(header().getByRole("link", { name: "Написать нам" }).getAttribute("href")).toBe("/contacts");
        cleanup();
        useAuth.setState({ ready: false, config: null, me: null });

        await openLanding("/about", config({ feedback_enabled: false, contacts: {} }));
        await screen.findByRole("heading", { level: 1 });
        expect(screen.queryByRole("link", { name: "Написать нам" })).toBeNull();
    });
});

describe("схема на лендинге", () => {
    it("у всех нод белый фон (раньше он терялся из-за оборванного класса)", async () => {
        await openLanding();
        for (const name of ["Почта", "ИИ-агент", "Нейросеть", "Отправить письмо", "Таблица", "Календарь"]) {
            const node = screen.getByTitle(name).parentElement as HTMLElement;
            expect(node.classList.contains("bg-white"), name).toBe(true);
            expect(node.className, name).not.toMatch(/bg-white-/);
        }
    });
});

describe("карточка «Локально и приватно»", () => {
    it("содержит ссылку на репозиторий на GitHub, которая открывается в новой вкладке безопасно", async () => {
        await openLanding();
        const card = (await screen.findByRole("heading", { level: 3, name: "Локально и приватно" })).parentElement as HTMLElement;
        const link = within(card).getByRole("link", { name: "Скачать с GitHub" });
        expect(link.getAttribute("href")).toBe("https://github.com/nikita-razgulyaev/FlowMind-AI");
        expect(link.getAttribute("target")).toBe("_blank");
        expect(link.getAttribute("rel")).toBe("noopener noreferrer");
        expect(within(card).getByText("docker compose up --build")).toBeTruthy();       // команда запуска на месте
        // а в облачной карточке ссылки нет
        const cloud = screen.getByRole("heading", { level: 3, name: "Облачная версия" }).parentElement as HTMLElement;
        expect(within(cloud).queryByRole("link")).toBeNull();
    });
});
