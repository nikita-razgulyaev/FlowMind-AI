import { Link, useLocation } from "react-router-dom";
import { Workflow, History, FileText, Plug, Settings } from "lucide-react";

const ITEMS: {
    to: string;
    icon: typeof Workflow;
    title: string;
    disabled?: boolean;
}[] = [
    { to: "/", icon: Workflow, title: "Воркфлоу" },
    { to: "/executions", icon: History, title: "История" },
    { to: "/templates", icon: FileText, title: "Шаблоны" },
    { to: "/connections", icon: Plug, title: "Подключения" },
];

export default function EditorSidebar() {
    const location = useLocation();

    return (
        <aside className="w-11 shrink-0 bg-white border-r border-gray-200 flex flex-col items-center py-3 gap-4">
            {ITEMS.map(({ to, icon: Icon, title, disabled }) => {
                const isActive = location.pathname === to;
                const cls = `p-1.5 rounded-lg transition-colors ${
                    disabled
                        ? "text-gray-300 cursor-not-allowed"
                        : isActive
                          ? "text-blue-600 bg-blue-50"
                          : "text-gray-400 hover:text-gray-600 hover:bg-gray-50"
                }`;
                return disabled ? (
                    <span key={title} className={cls} title={title}>
                        <Icon className="w-[18px] h-[18px]" />
                    </span>
                ) : (
                    <Link key={to} to={to} className={cls} title={title}>
                        <Icon className="w-[18px] h-[18px]" />
                    </Link>
                );
            })}
            <div className="flex-1" />
            <Link
                to="/settings"
                className={`p-1.5 rounded-lg transition-colors ${
                    location.pathname === "/settings"
                        ? "text-blue-600 bg-blue-50"
                        : "text-gray-400 hover:text-gray-600 hover:bg-gray-50"
                }`}
                title="Настройки"
            >
                <Settings className="w-[18px] h-[18px]" />
            </Link>
        </aside>
    );
}
