import { Link, useLocation, useNavigate } from "react-router-dom";
import { Workflow, History, FileText, Plug, Settings, UserCircle, ShieldCheck, LogOut, CreditCard, Info } from "lucide-react";
import { useAuth } from "../../store/auth";

const ITEMS: { to: string; icon: typeof Workflow; title: string }[] = [
    { to: "/", icon: Workflow, title: "Воркфлоу" },
    { to: "/executions", icon: History, title: "История" },
    { to: "/templates", icon: FileText, title: "Шаблоны" },
    { to: "/connections", icon: Plug, title: "Подключения" },
];

export default function EditorSidebar() {
    const location = useLocation();
    const navigate = useNavigate();
    const { config, me, logout } = useAuth();
    const showAccount = !!config?.auth_required;
    const isAdmin = me?.user.role === "admin" && showAccount;

    const linkClass = (active: boolean) =>
        `p-1.5 rounded-lg transition-colors ${
            active ? "text-blue-600 bg-blue-50" : "text-gray-400 hover:text-gray-600 hover:bg-gray-50"
        }`;

    return (
        <aside className="w-11 shrink-0 bg-white border-r border-gray-200 flex flex-col items-center py-3 gap-4">
            {ITEMS.map(({ to, icon: Icon, title }) => (
                <Link key={to} to={to} className={linkClass(location.pathname === to)} title={title}>
                    <Icon className="w-[18px] h-[18px]" />
                </Link>
            ))}
            <div className="flex-1" />
            {showAccount && (
                <>
                    <Link to="/pricing" className={linkClass(location.pathname === "/pricing")} title="Тарифы">
                        <CreditCard className="w-[18px] h-[18px]" />
                    </Link>
                    <Link to="/about" className={linkClass(location.pathname === "/about")} title="О сервисе">
                        <Info className="w-[18px] h-[18px]" />
                    </Link>
                </>
            )}
            {isAdmin && (
                <Link to="/admin" className={linkClass(location.pathname.startsWith("/admin"))} title="Админ-панель">
                    <ShieldCheck className="w-[18px] h-[18px]" />
                </Link>
            )}
            {showAccount && (
                <Link to="/account" className={linkClass(location.pathname === "/account")} title="Личный кабинет">
                    <UserCircle className="w-[18px] h-[18px]" />
                </Link>
            )}
            <Link to="/settings" className={linkClass(location.pathname === "/settings")} title="Настройки">
                <Settings className="w-[18px] h-[18px]" />
            </Link>
            {showAccount && (
                <button
                    className={linkClass(false)}
                    title="Выйти"
                    onClick={async () => {
                        await logout();
                        navigate("/");
                    }}
                >
                    <LogOut className="w-[18px] h-[18px]" />
                </button>
            )}
        </aside>
    );
}
