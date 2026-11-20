import { defineConfig } from "vitepress";

// Сайт публикуется самим сервисом по адресу /help/ (см. Dockerfile и backend/app/main.py).
export default defineConfig({
    lang: "ru-RU",
    title: "FlowMind AI",
    description: "Документация визуального конструктора AI-агентов и автоматизаций",
    base: "/help/",
    head: [["link", { rel: "icon", href: "/help/logo.svg" }]],
    cleanUrls: false,
    srcExclude: ["README.md"],
    ignoreDeadLinks: [/^https?:\/\/localhost/],
    appearance: false,

    themeConfig: {
        logo: "/logo.svg",
        siteTitle: "FlowMind AI",

        nav: [
            { text: "Справочник", link: "/guide/", activeMatch: "^/(guide|steps|admin)/" },
            { text: "История изменений", link: "/changelog" },
        ],
        logoLink: "/guide/",


        // Один общий сайдбар: руководство → шаги → установка
        sidebar: [
            {
                text: "Начало работы",
                items: [
                    { text: "О FlowMind AI", link: "/guide/" },
                    { text: "Быстрый старт", link: "/guide/quick-start" },
                    { text: "Основные понятия", link: "/guide/concepts" },
                ],
            },
            {
                text: "Работа в редакторе",
                items: [
                    { text: "Редактор сценариев", link: "/guide/editor" },
                    { text: "Данные между шагами", link: "/guide/data-between-steps" },
                    { text: "Проверка сценария и шага", link: "/guide/checking" },
                    { text: "ИИ-помощник", link: "/guide/ai-assistant" },
                    { text: "Готовые шаблоны", link: "/guide/templates" },
                ],
            },
            {
                text: "Запуск и подключения",
                items: [
                    { text: "Запуск и история", link: "/guide/runs" },
                    { text: "Подключения", link: "/guide/connections" },
                    { text: "Тарифы и лимиты", link: "/guide/plans" },
                    { text: "Частые вопросы", link: "/guide/faq" },
                ],
            },
            {
                text: "Справочник по шагам",
                items: [
                    { text: "Все шаги", link: "/steps/" },
                    { text: "Запуск", link: "/steps/triggers" },
                    { text: "Нейросеть", link: "/steps/ai" },
                    { text: "Ветвление", link: "/steps/logic" },
                    { text: "Текст и данные", link: "/steps/data" },
                    { text: "Сервисы и отправка", link: "/steps/apps" },
                ],
            },
            {
                text: "Установка и настройка",
                items: [
                    { text: "Установка", link: "/admin/installation" },
                    { text: "Переменные окружения", link: "/admin/configuration" },
                    { text: "Публикация в облаке", link: "/admin/deployment" },
                    { text: "Админ-панель", link: "/admin/administration" },
                ],
            },
            {
                text: "Для разработчиков",
                items: [
                    { text: "Архитектура", link: "/admin/architecture" },
                    { text: "HTTP API", link: "/admin/api" },
                    { text: "Безопасность", link: "/admin/security" },
                    { text: "Разработка", link: "/admin/development" },
                    { text: "История изменений", link: "/changelog" },
                ],
            },
        ],

        search: { provider: "local" },
        outline: { label: "На этой странице", level: [2, 3] },
        socialLinks: [],
        footer: {
            message: "",
            copyright: "© 2026 FlowMind AI",
        },
        docFooter: {
            prev: "Назад",
            next: "Далее",
        },
        returnToTopLabel: "Наверх",
        sidebarMenuLabel: "Меню",
            },
});
