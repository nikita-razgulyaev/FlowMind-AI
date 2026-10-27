import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { Loader2 } from "lucide-react";

const BUTTON_VARIANTS = {
    primary: "bg-blue-600 text-white hover:bg-blue-700",
    secondary: "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50",
    danger: "bg-red-600 text-white hover:bg-red-700",
    ghost: "text-gray-600 hover:bg-gray-100",
    success: "bg-emerald-600 text-white hover:bg-emerald-700",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: keyof typeof BUTTON_VARIANTS;
    loading?: boolean;
    size?: "sm" | "md" | "lg";
}

export function Button({ variant = "primary", loading, size = "md", className = "", children, disabled, ...rest }: ButtonProps) {
    const sizes = { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2 text-sm", lg: "px-6 py-3 text-base" };
    return (
        <button
            {...rest}
            disabled={disabled || loading}
            className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${sizes[size]} ${BUTTON_VARIANTS[variant]} ${className}`}
        >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            {children}
        </button>
    );
}

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
    label: string;
    hint?: string;
}

export function Field({ label, hint, className = "", ...rest }: FieldProps) {
    return (
        <label className="block">
            <span className="block text-sm font-medium text-gray-700 mb-1">{label}</span>
            <input
                {...rest}
                className={`w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50 ${className}`}
            />
            {hint && <span className="block text-xs text-gray-400 mt-1">{hint}</span>}
        </label>
    );
}

export function Select({ label, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
    return (
        <label className="block">
            {label && <span className="block text-sm font-medium text-gray-700 mb-1">{label}</span>}
            <select {...rest} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500">
                {children}
            </select>
        </label>
    );
}

const ALERT_STYLES = {
    error: "bg-red-50 text-red-700 border-red-200",
    success: "bg-emerald-50 text-emerald-700 border-emerald-200",
    info: "bg-blue-50 text-blue-700 border-blue-200",
    warning: "bg-amber-50 text-amber-800 border-amber-200",
};

export function Alert({ type = "info", children }: { type?: keyof typeof ALERT_STYLES; children: ReactNode }) {
    return <div className={`text-sm rounded-lg border px-3 py-2 ${ALERT_STYLES[type]}`}>{children}</div>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
    return <div className={`bg-white border border-gray-200 rounded-xl shadow-sm ${className}`}>{children}</div>;
}

export function Spinner({ label }: { label?: string }) {
    return (
        <div className="flex items-center justify-center gap-2 py-10 text-gray-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin" />
            {label}
        </div>
    );
}

const BADGE_STYLES = {
    gray: "bg-gray-100 text-gray-700",
    blue: "bg-blue-100 text-blue-700",
    green: "bg-emerald-100 text-emerald-700",
    red: "bg-red-100 text-red-700",
    amber: "bg-amber-100 text-amber-800",
    indigo: "bg-indigo-100 text-indigo-700",
};

export function Badge({ color = "gray", children }: { color?: keyof typeof BADGE_STYLES; children: ReactNode }) {
    return <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full ${BADGE_STYLES[color]}`}>{children}</span>;
}

/** Прогресс использования лимита; limit = null означает «без ограничений». */
export function UsageBar({ label, used, limit }: { label: string; used: number; limit: number | null }) {
    const percent = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
    const color = percent >= 100 ? "bg-red-500" : percent >= 80 ? "bg-amber-500" : "bg-blue-500";
    return (
        <div>
            <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-700">{label}</span>
                <span className="text-gray-500 tabular-nums">
                    {used.toLocaleString("ru-RU")} / {limit === null ? "∞" : limit.toLocaleString("ru-RU")}
                </span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className={`h-full ${color} transition-all`} style={{ width: limit === null ? "0%" : `${percent}%` }} />
            </div>
        </div>
    );
}
