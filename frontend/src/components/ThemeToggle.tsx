import { Moon, Sun } from "lucide-react";
import { useTheme } from "../hooks/useTheme";

/** Кнопка переключения светлой/тёмной темы (как в документации VitePress). */
export default function ThemeToggle({ className = "" }: { className?: string }) {
    const { isDark, toggle } = useTheme();
    return (
        <button
            type="button"
            onClick={toggle}
            className={`inline-flex items-center justify-center rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-[rgba(235,235,245,0.6)] dark:hover:bg-[#202127] dark:hover:text-[rgba(255,255,245,0.86)] transition-colors ${className}`}
            title={isDark ? "Светлая тема" : "Тёмная тема"}
            aria-label={isDark ? "Включить светлую тему" : "Включить тёмную тему"}
        >
            {isDark ? <Sun className="w-[18px] h-[18px]" /> : <Moon className="w-[18px] h-[18px]" />}
        </button>
    );
}
