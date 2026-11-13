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
    emailForm?: boolean; // особая форма: выбор почтового сервиса, адрес и пароль приложения
    oauth?: boolean; // подключается через вход в аккаунт сервиса, а не через форму с полями
    family?: "google" | "yandex" | "mailru"; // кто выдаёт доступ
    service?: string; // как называется сервис на кнопке входа
    guide?: string; // пошаговая инструкция под формой
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
            { key: "models", label: "Модели через запятую (необязательно)", type: "text", placeholder: "openai/gpt-oss-120b:groq" },
        ],
        note: "Облачные шаги «Нейросеть» и «ИИ-агент» через Hugging Face (поддерживает работу агента с инструментами)",
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
            { key: "models", label: "Модели через запятую (необязательно)", type: "text", placeholder: "gpt-4o-mini, gpt-4o" },
        ],
        note: "OpenAI, OpenRouter, Groq и другие совместимые провайдеры",
    },
    {
        key: "telegram_bot",
        label: "Telegram-бот (канал или чат)",
        category: "tool",
        fields: [
            {
                key: "bot_token",
                label: "Токен бота",
                type: "password",
                placeholder: "123456:ABC-DEF...",
            },
        ],
        guide: "1) В Telegram откройте @BotFather и отправьте /newbot. 2) Скопируйте выданный токен сюда. 3) Чтобы публиковать в канал, добавьте бота в канал администратором с правом публикации сообщений. Токен проверяется сразу при подключении.",
        note: "Один и тот же бот используется и для отправки, и для приёма входящих сообщений",
        usedFor: "прослушка ТГ · ответ на сообщение",
    },
    {
        key: "google_sheets",
        label: "Google Таблицы",
        category: "tool",
        fields: [],
        oauth: true,
        family: "google",
        service: "Google",
        note: "Вход через Google — доступ только к Таблицам",
        usedFor: "занесение клиента в таблицу",
    },
    {
        key: "yandex_sheets",
        label: "Яндекс Таблицы",
        category: "tool",
        fields: [],
        oauth: true,
        family: "yandex",
        service: "Яндекс",
        note: "Вход через Яндекс — доступ к файлам Таблиц на Диске",
        usedFor: "занесение клиента в таблицу",
    },
    {
        key: "yandex_calendar",
        label: "Яндекс Календарь",
        category: "tool",
        fields: [
            { key: "email", label: "Адрес Яндекс Почты", type: "text", placeholder: "login@yandex.ru" },
            { key: "password", label: "Пароль приложения для «Календаря»", type: "password", placeholder: "" },
        ],
        guide: "Яндекс подключается по протоколу CalDAV. Создайте пароль приложения: Яндекс ID → Безопасность → Пароли приложений → тип «Календарь». Новый пароль может начать действовать через 2–3 часа.",
        usedFor: "создание событий",
    },
    {
        key: "google_gmail",
        label: "Gmail (вход через Google)",
        category: "tool",
        fields: [],
        oauth: true,
        family: "google",
        service: "Google",
        note: "Пароль не нужен. Доступ к почте можно отозвать в настройках аккаунта Google в любой момент",
        usedFor: "приём писем · ответ на письмо",
    },
    {
        key: "yandex_mail",
        label: "Яндекс Почта (вход через Яндекс)",
        category: "tool",
        fields: [],
        oauth: true,
        family: "yandex",
        service: "Яндекс",
        note: "Пароль не нужен: доступ выдаётся через Яндекс ID",
        usedFor: "приём писем · ответ на письмо",
    },
    {
        key: "mailru_mail",
        label: "Почта Mail.ru (вход через Mail.ru)",
        category: "tool",
        fields: [],
        oauth: true,
        family: "mailru",
        service: "Mail.ru",
        note: "Пароль не нужен: доступ выдаётся через Mail.ru",
        usedFor: "приём писем · ответ на письмо",
    },
    {
        key: "email",
        label: "Почта по паролю приложения",
        category: "tool",
        fields: [],
        emailForm: true,
        note: "Запасной вариант, если у почты нет входа через аккаунт: Outlook, корпоративная почта. Нужна пароль приложения, а не основной пароль",
        usedFor: "приём писем · ответ на письмо",
    },
    {
        key: "google_calendar",
        label: "Google Календарь",
        category: "tool",
        fields: [],
        oauth: true,
        family: "google",
        service: "Google",
        note: "Вход через Google — доступ только к Календарю",
        usedFor: "планирование встречи",
    },
];

export function getProvider(key: string): ProviderDef | undefined {
    return PROVIDERS.find((p) => p.key === key);
}


/** Почтовые сервисы: адреса серверов подставляются автоматически (совпадают с backend/app/services/email_service.py). */
export const EMAIL_PRESETS: { key: string; label: string; help: string }[] = [
    { key: "gmail", label: "Gmail", help: "Включите двухэтапную аутентификацию в аккаунте Google и создайте «пароль приложения». Обычный пароль не подойдёт." },
    { key: "mailru", label: "Почта Mail.ru", help: "В настройках Mail.ru откройте «Пароли для внешних приложений» и создайте пароль для почтовых программ." },
    { key: "yandex", label: "Яндекс Почта", help: "В настройках Яндекс Почты включите доступ по IMAP и создайте пароль приложения." },
    { key: "outlook", label: "Outlook / Microsoft 365", help: "Для рабочих аккаунтов Microsoft 365 администратор должен разрешить доступ по IMAP и SMTP." },
    { key: "custom", label: "Другая (корпоративная) почта", help: "Адреса серверов и порты можно узнать у хостинг-провайдера или IT-специалиста." },
];


/** Как пользователь выбирает подключение: что подключить → сервис → способ входа. Всё внутри одного окна. */
export interface ConnectMethod {
    label: string;
    providerKey: string;
    presets?: string[]; // для почты по паролю: допустимые почтовые сервисы
}
export interface ConnectService {
    label: string;
    methods: ConnectMethod[];
}
export interface ConnectGroup {
    key: string;
    label: string;
    services: ConnectService[];
}

export const TOOL_GROUPS: ConnectGroup[] = [
    {
        key: "telegram",
        label: "Telegram-бот (канал или чат)",
        services: [{ label: "Telegram", methods: [{ label: "Токен бота из @BotFather", providerKey: "telegram_bot" }] }],
    },
    {
        key: "mail",
        label: "Почта",
        services: [
            {
                label: "Gmail",
                methods: [
                    { label: "Через страницу входа Google (без пароля)", providerKey: "google_gmail" },
                    { label: "По паролю приложения", providerKey: "email", presets: ["gmail"] },
                ],
            },
            {
                label: "Яндекс Почта",
                methods: [
                    { label: "Через страницу входа Яндекса (без пароля)", providerKey: "yandex_mail" },
                    { label: "По паролю приложения", providerKey: "email", presets: ["yandex"] },
                ],
            },
            {
                label: "Почта Mail.ru",
                methods: [
                    { label: "Через страницу входа Mail.ru (без пароля)", providerKey: "mailru_mail" },
                    { label: "По паролю приложения", providerKey: "email", presets: ["mailru"] },
                ],
            },
            {
                label: "Outlook / Microsoft 365",
                methods: [
                    { label: "По паролю приложения", providerKey: "email", presets: ["outlook"] },
                ],
            },
            {
                label: "Корпоративная / другая почта",
                methods: [
                    { label: "По паролю приложения", providerKey: "email", presets: ["custom"] },
                ],
            },
        ],
    },
    {
        key: "sheets",
        label: "Таблицы",
        services: [
            { label: "Google Таблицы", methods: [{ label: "Через страницу входа Google", providerKey: "google_sheets" }] },
            { label: "Яндекс Таблицы", methods: [{ label: "Через страницу входа Яндекса", providerKey: "yandex_sheets" }] },
        ],
    },
    {
        key: "calendar",
        label: "Календарь",
        services: [
            { label: "Google Календарь", methods: [{ label: "Через страницу входа Google", providerKey: "google_calendar" }] },
            { label: "Яндекс Календарь", methods: [{ label: "По паролю приложения", providerKey: "yandex_calendar" }] },
        ],
    },
];
