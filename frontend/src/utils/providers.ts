export interface ProviderField {
    key: string;
    label: string;
    type: "text" | "password";
    placeholder?: string;
}

export interface ProviderDef {
    key: string;
    label: string;
    category: "ai_api" | "tool";
    fields: ProviderField[];
    note?: string;
    usedFor?: string;
    comingSoon?: boolean;
    oauth?: boolean; // подключается через "Войти через Google", а не через форму с полями
}

export const PROVIDERS: ProviderDef[] = [
    {
        key: "huggingface",
        label: "Hugging Face",
        category: "ai_api",
        fields: [
            {
                key: "api_key",
                label: "API Key",
                type: "password",
                placeholder: "hf_...",
            },
        ],
        note: "Облачные LLM/Agent-ноды (mode: cloud)",
    },
    {
        key: "openai_compatible",
        label: "OpenAI-совместимый API",
        category: "ai_api",
        fields: [
            {
                key: "base_url",
                label: "Base URL",
                type: "text",
                placeholder: "https://api.openai.com/v1",
            },
            { key: "api_key", label: "API Key", type: "password" },
        ],
        note: "OpenAI, OpenRouter, Groq и другие совместимые провайдеры",
    },
    {
        key: "telegram_bot",
        label: "Telegram Bot",
        category: "tool",
        fields: [
            {
                key: "bot_token",
                label: "Bot Token",
                type: "password",
                placeholder: "123456:ABC-DEF...",
            },
        ],
        note: "Один и тот же бот используется и для отправки, и для прослушки входящих сообщений",
        usedFor: "прослушка ТГ · ответ на сообщение",
    },
    {
        key: "google_sheets",
        label: "Google Таблицы",
        category: "tool",
        fields: [],
        oauth: true,
        note: "Вход через Google — доступ только к Таблицам",
        usedFor: "занесение клиента в таблицу",
    },
    {
        key: "google_calendar",
        label: "Google Календарь",
        category: "tool",
        fields: [],
        oauth: true,
        note: "Вход через Google — доступ только к Календарю",
        usedFor: "планирование встречи",
    },
];

export function getProvider(key: string): ProviderDef | undefined {
    return PROVIDERS.find((p) => p.key === key);
}
