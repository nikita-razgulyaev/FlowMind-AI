import { h } from "vue";
import type { Theme } from "vitepress";
import DefaultTheme from "vitepress/theme";
import "./custom.css";

/** Уйти из SPA документации на корень приложения (полный reload). */
function goToApp(e: Event) {
    e.preventDefault();
    e.stopPropagation();
    window.location.href = "/";
}

export default {
    extends: DefaultTheme,
    Layout() {
        return h(DefaultTheme.Layout, null, {
            "nav-bar-content-after": () =>
                h(
                    "a",
                    {
                        class: "back-to-app",
                        href: "/",
                        title: "Вернуться в сервис",
                        // не давать VitePress перехватывать как внутреннюю ссылку
                        rel: "noopener",
                        onClick: goToApp,
                        onMouseDown: (e: MouseEvent) => {
                            // middle-click / default — тоже на корень приложения
                            if (e.button === 0) goToApp(e);
                        },
                    },
                    "Открыть сервис →",
                ),
        });
    },
} satisfies Theme;
