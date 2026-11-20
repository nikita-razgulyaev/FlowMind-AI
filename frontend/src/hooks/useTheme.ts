import { useCallback, useEffect, useState } from "react";

export type ThemeMode = "light" | "dark";

const STORAGE_KEY = "fm-theme";

function readStored(): ThemeMode {
    try {
        const v = localStorage.getItem(STORAGE_KEY);
        if (v === "dark" || v === "light") return v;
    } catch { /* ignore */ }
    if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        return "dark";
    }
    return "light";
}

function applyDom(mode: ThemeMode) {
    const root = document.documentElement;
    if (mode === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
    root.style.colorScheme = mode;
}

/** Тема интерфейса: light | dark. Сохраняется в localStorage, применяется к <html class="dark">. */
export function useTheme() {
    const [theme, setThemeState] = useState<ThemeMode>(() =>
        typeof document !== "undefined" && document.documentElement.classList.contains("dark") ? "dark" : "light",
    );

    useEffect(() => {
        const mode = readStored();
        setThemeState(mode);
        applyDom(mode);
    }, []);

    const setTheme = useCallback((mode: ThemeMode) => {
        setThemeState(mode);
        applyDom(mode);
        try {
            localStorage.setItem(STORAGE_KEY, mode);
        } catch { /* ignore */ }
    }, []);

    const toggle = useCallback(() => {
        setTheme(theme === "dark" ? "light" : "dark");
    }, [theme, setTheme]);

    return { theme, setTheme, toggle, isDark: theme === "dark" };
}
