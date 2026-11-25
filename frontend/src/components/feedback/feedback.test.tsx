// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../../i18n";
import { api } from "../../api/client";
import { useAuth } from "../../store/auth";
import type { FeedbackItem } from "../../types/app";
import AdminFeedback from "../../pages/admin/AdminFeedback";
import ContactsList from "./ContactsList";
import FeedbackForm from "./FeedbackForm";

vi.mock("../../api/client", async (importOriginal) => {
    const actual = await importOriginal<typeof import("../../api/client")>();
    return {
        ...actual,
        api: {
            sendFeedback: vi.fn(),
            adminFeedback: vi.fn(),
            adminFeedbackUpdate: vi.fn(),
            adminFeedbackDelete: vi.fn(),
            adminFeedbackClearSpam: vi.fn(),
            adminFeedbackForward: vi.fn(),
            adminFeedbackCsv: vi.fn(),
        },
    };
});

const sendFeedback = vi.mocked(api.sendFeedback);

beforeEach(() => {
    sendFeedback.mockResolvedValue({ data: { ok: true } } as never);
    useAuth.setState({ me: null, config: null });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const send = () => screen.getByRole("button", { name: "Отправить" });
const textarea = () => screen.getByRole("textbox", { name: /Сообщение/ });
const trap = () => screen.getByTestId("feedback-trap") as HTMLInputElement;

describe("ловушка для ботов", () => {
    it("скрыта от людей, скринридеров и клавиатуры и по умолчанию пуста", () => {
        render(<FeedbackForm />);
        const input = trap();
        expect(input.value).toBe("");
        expect(input.tabIndex).toBe(-1);
        expect(input.getAttribute("autocomplete")).toBe("off");
        expect(input.closest("[aria-hidden='true']")).not.toBeNull();
        // не «display:none» (такие поля часть ботов пропускает), а вынесена за экран
        expect(input.parentElement?.style.left).toBe("-10000px");
        // имя не из тех, что браузеры автозаполняют адресом, сайтом или телефоном
        expect(input.name).not.toMatch(/url|site|web|phone|address|company|email|name/i);
    });

    it("клавиатурный обход формы не попадает в ловушку", async () => {
        const user = userEvent.setup();
        render(<FeedbackForm />);
        textarea().focus();
        for (let i = 0; i < 12; i++) {
            await user.tab();
            expect(document.activeElement).not.toBe(trap());
        }
    });

    it("обычный человек отправляет пустую ловушку", async () => {
        const user = userEvent.setup();
        render(<FeedbackForm />);
        await user.type(textarea(), "Не работает кнопка запуска");
        await user.click(send());
        expect(sendFeedback).toHaveBeenCalledTimes(1);
        expect(sendFeedback.mock.calls[0][0].hp).toBe("");
    });

    it("заполненную ловушку (бот) отправляет как есть, а бот видит такой же успех, как человек", async () => {
        const user = userEvent.setup();
        render(<FeedbackForm />);
        await user.type(textarea(), "Купите SEO-продвижение");
        fireEvent.change(trap(), { target: { value: "http://spam.example" } });
        await user.click(send());
        expect(sendFeedback.mock.calls[0][0].hp).toBe("http://spam.example");
        expect(await screen.findByText("Спасибо, обращение отправлено!")).toBeTruthy();
    });
});

describe("внешний вид полей", () => {
    it("у каждого поля своё кольцо фокуса, а стандартная обводка браузера отключена (без двойной рамки)", () => {
        render(<FeedbackForm />);
        const fields = [screen.getByRole("combobox"), textarea(), screen.getByLabelText(/Имя/), screen.getByLabelText(/Email для ответа/)];
        for (const field of fields) {
            expect(field.className).toContain("focus:ring-2");
            expect(field.className).toContain("focus:outline-hidden");
        }
    });

    it("тексты формы", () => {
        render(<FeedbackForm />);
        expect(textarea().getAttribute("placeholder")).toBe("Что вас интересует или что хотите предложить? Если это ошибка — опишите, что делали и что произошло");
    });
});

describe("отправка", () => {
    it("передаёт тип, очищенный текст, страницу без query, ключ повторной отправки и время заполнения", async () => {
        window.history.pushState({}, "", "/connections?token=SECRET#frag");
        const user = userEvent.setup();
        render(<FeedbackForm />);
        await user.selectOptions(screen.getByRole("combobox"), "bug");
        await user.type(textarea(), "   Бот не отвечает   ");
        await user.type(screen.getByLabelText(/Email для ответа/), "ivan@example.com");
        await user.click(send());

        const body = sendFeedback.mock.calls[0][0];
        expect(body).toMatchObject({ type: "bug", message: "Бот не отвечает", email: "ivan@example.com", page: "/connections", hp: "" });
        expect(body.client_id.length).toBeGreaterThanOrEqual(8);
        expect(body.elapsed_ms).toBeGreaterThanOrEqual(0);
        expect(JSON.stringify(body)).not.toContain("SECRET");
        window.history.pushState({}, "", "/");
    });

    it("проверяет текст и email до отправки и ничего не шлёт", async () => {
        const user = userEvent.setup();
        render(<FeedbackForm />);
        await user.type(textarea(), "ок");
        await user.click(send());
        expect(screen.getByText("Напишите хотя бы 3 символа")).toBeTruthy();

        await user.type(textarea(), "ок!");
        await user.type(screen.getByLabelText(/Email для ответа/), "не-почта");
        await user.click(send());
        expect(screen.getByText("Проверьте адрес почты")).toBeTruthy();
        expect(sendFeedback).not.toHaveBeenCalled();
    });

    it("email необязателен", async () => {
        const user = userEvent.setup();
        render(<FeedbackForm />);
        await user.type(textarea(), "Анонимная идея про шаблоны");
        await user.click(send());
        expect(sendFeedback).toHaveBeenCalledTimes(1);
    });

    it("при ошибке сохраняет текст и повторяет отправку с тем же ключом", async () => {
        sendFeedback.mockResolvedValueOnce({ data: null, error: "Сервер временно недоступен." } as never);
        const user = userEvent.setup();
        render(<FeedbackForm />);
        await user.type(textarea(), "Длинное описание проблемы, которое жалко терять");
        await user.click(send());

        expect(await screen.findByText(/Сервер временно недоступен/)).toBeTruthy();
        expect((textarea() as HTMLTextAreaElement).value).toBe("Длинное описание проблемы, которое жалко терять");

        await user.click(send());
        expect(await screen.findByText("Спасибо, обращение отправлено!")).toBeTruthy();
        expect(sendFeedback.mock.calls[1][0].client_id).toBe(sendFeedback.mock.calls[0][0].client_id);
    });

    it("не даёт отправить дважды, пока идёт запрос", async () => {
        let resolve: (v: unknown) => void = () => {};
        sendFeedback.mockReturnValueOnce(new Promise((r) => { resolve = r; }) as never);
        const user = userEvent.setup();
        render(<FeedbackForm />);
        await user.type(textarea(), "Двойной клик");
        await user.click(send());
        await user.click(send());
        expect(sendFeedback).toHaveBeenCalledTimes(1);
        resolve({ data: { ok: true } });
        await screen.findByText("Спасибо, обращение отправлено!");
    });

    it("после успеха можно написать ещё — с новым ключом и пустым полем", async () => {
        const user = userEvent.setup();
        render(<FeedbackForm />);
        await user.type(textarea(), "Первое обращение");
        await user.click(send());
        await user.click(await screen.findByRole("button", { name: "Написать ещё" }));
        expect((textarea() as HTMLTextAreaElement).value).toBe("");
        await user.type(textarea(), "Второе обращение");
        await user.click(send());
        expect(sendFeedback.mock.calls[1][0].client_id).not.toBe(sendFeedback.mock.calls[0][0].client_id);
    });

    it("подставляет имя и почту вошедшего пользователя", () => {
        useAuth.setState({ me: { user: { name: "Анна", email: "anna@example.com" } } as never });
        render(<FeedbackForm />);
        expect((screen.getByLabelText(/Имя/) as HTMLInputElement).value).toBe("Анна");
        expect((screen.getByLabelText(/Email для ответа/) as HTMLInputElement).value).toBe("anna@example.com");
    });

    it("восстановленный черновик не считается «слишком быстрой» отправкой", async () => {
        const user = userEvent.setup();
        render(<FeedbackForm draft="Черновик, начатый раньше" />);
        await user.click(send());
        expect(sendFeedback.mock.calls[0][0].elapsed_ms).toBeGreaterThanOrEqual(60_000);
    });
});

describe("контакты", () => {
    const contacts = { email: "help@flowmind.example", telegram: { label: "@flowmind", url: "https://t.me/flowmind" } };

    it("показывает только заполненные и открывает внешние ссылки безопасно", () => {
        render(<ContactsList contacts={contacts} />);
        expect(screen.getByRole("link", { name: /help@flowmind.example/ }).getAttribute("href")).toBe("mailto:help@flowmind.example");
        const tg = screen.getByRole("link", { name: /Telegram/ });
        expect(tg.getAttribute("href")).toBe("https://t.me/flowmind");
        expect(tg.getAttribute("rel")).toBe("noopener noreferrer");
        expect(tg.getAttribute("target")).toBe("_blank");
        expect(screen.queryByText("ВКонтакте")).toBeNull();
    });

    it("ничего не рисует, если контактов нет", () => {
        const { container } = render(<ContactsList contacts={{}} />);
        expect(container.innerHTML).toBe("");
    });
});

describe("админка: показ отзывов", () => {
    const item = (over: Partial<FeedbackItem>): FeedbackItem => ({
        id: 1, created_at: "2026-11-24T10:00:00Z", status: "new", type: "bug", name: "", email: "a@example.com", plan: "free", user_id: 5,
        message: "текст", page: "/", user_agent: "", spam_reason: "", admin_note: "", forward_status: "sent", ...over,
    });

    it("HTML и скрипты из текста отзыва выводятся как текст и не исполняются", async () => {
        const evil = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=2</script>';
        vi.mocked(api.adminFeedback).mockResolvedValue({
            data: { total: 1, items: [item({ message: evil, name: "<b>Имя</b>" })], counts: { new: 1, in_progress: 0, done: 0, spam: 0 } },
        } as never);
        const { container } = render(<AdminFeedback />);
        expect(await screen.findByText(evil)).toBeTruthy();
        expect(container.querySelector("img")).toBeNull();
        expect(container.querySelector("script")).toBeNull();
        expect(container.querySelector("b")).toBeNull();
        expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
    });

    it("спам показывает причину и кнопку «Это не спам»", async () => {
        vi.mocked(api.adminFeedback).mockResolvedValue({
            data: { total: 1, items: [item({ status: "spam", spam_reason: "honeypot", forward_status: "off" })], counts: { new: 0, in_progress: 0, done: 0, spam: 1 } },
        } as never);
        render(<AdminFeedback />);
        expect(await screen.findByText("заполнено скрытое поле (бот)")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Это не спам" })).toBeTruthy();
        await waitFor(() => expect(api.adminFeedback).toHaveBeenCalled());
    });
});
