import { Link, useLocation, useNavigate } from "react-router-dom";
import { useState, type ReactNode, type MouseEvent } from "react";
import { GraduationCap, Library, Workflow, History, FileText, Plug, Settings, UserCircle, ShieldCheck, LogOut, CreditCard, Info } from "lucide-react";
import { useAuth } from "../../store/auth";
import TutorialModal from "../tutorial/TutorialModal";
import ConfirmDialog from "../ConfirmDialog";

const ITEMS: { to: string; icon: typeof Workflow; title: string }[] = [
    { to: "/", icon: Workflow, title: "Мои сценарии" },
    { to: "/executions", icon: History, title: "История запусков" },
    { to: "/templates", icon: FileText, title: "Готовые шаблоны" },
    { to: "/connections", icon: Plug, title: "Подключения (Telegram, почта, Google)" },
];

type Props = {
    /**
     * Если задан — перед уходом по ссылке сайдбара вызывается этот колбэк.
     * Чтобы всё же уйти, нужно вызвать `proceed()`.
     * Используется редактором сценария для предупреждения о несохранённых изменениях.
     */
    onLeaveRequest?: (proceed: () => void) => void;
};

export default function EditorSidebar({ onLeaveRequest }: Props = {}) {
    const location = useLocation();
    const navigate = useNavigate();
    const { config, me, logout } = useAuth();
    const [logoutOpen, setLogoutOpen] = useState(false);
    const [tutorialOpen, setTutorialOpen] = useState(false);
    const showAccount = !!config?.auth_required;
    const isAdmin = me?.user.role === "admin" && showAccount;

    const linkClass = (active: boolean) =>
        `p-1.5 rounded-lg transition-colors ${
            active ? "text-blue-600 bg-blue-50" : "text-gray-400 hover:text-gray-600 hover:bg-gray-50"
        }`;

    const go = (to: string) => {
        if (onLeaveRequest) onLeaveRequest(() => navigate(to));
        else navigate(to);
    };

    const GuardedLink = ({ to, title, children, active }: { to: string; title: string; children: ReactNode; active: boolean }) => {
        if (!onLeaveRequest) {
            return (
                <Link to={to} className={linkClass(active)} title={title}>
                    {children}
                </Link>
            );
        }
        return (
            <button
                type="button"
                className={linkClass(active)}
                title={title}
                onClick={(e: MouseEvent) => {
                    e.preventDefault();
                    go(to);
                }}
            >
                {children}
            </button>
        );
    };

    return (
        <aside className="w-11 shrink-0 bg-white border-r border-gray-200 flex flex-col items-center py-3 gap-4">
            {ITEMS.map(({ to, icon: Icon, title }) => (
                <GuardedLink key={to} to={to} title={title} active={location.pathname === to}>
                    <Icon className="w-[18px] h-[18px]" />
                </GuardedLink>
            ))}
            <div className="flex-1" />
            <button
                className={linkClass(tutorialOpen)}
                title="Обучение: как собрать сценарий. Там же можно открыть новый сценарий с пошаговой подсказкой"
                aria-label="Обучение"
                onClick={() => setTutorialOpen(true)}
            >
                <GraduationCap className="w-[18px] h-[18px]" />
            </button>
            <a
                href="/help/guide/"
                target="_blank"
                rel="noopener noreferrer"
                className={linkClass(false)}
                title="Документация (откроется в новой вкладке)"
                aria-label="Документация"
            >
                <Library className="w-[18px] h-[18px]" />
            </a>
            {showAccount && (
                <>
                    <GuardedLink to="/pricing" title="Тарифы" active={location.pathname === "/pricing"}>
                        <CreditCard className="w-[18px] h-[18px]" />
                    </GuardedLink>
                    <GuardedLink to="/about" title="О сервисе" active={location.pathname === "/about"}>
                        <Info className="w-[18px] h-[18px]" />
                    </GuardedLink>
                </>
            )}
            {isAdmin && (
                <GuardedLink to="/admin" title="Админ-панель" active={location.pathname.startsWith("/admin")}>
                    <ShieldCheck className="w-[18px] h-[18px]" />
                </GuardedLink>
            )}
            {showAccount && (
                <GuardedLink to="/account" title="Личный кабинет" active={location.pathname === "/account"}>
                    <UserCircle className="w-[18px] h-[18px]" />
                </GuardedLink>
            )}
            <GuardedLink to="/settings" title="Настройки" active={location.pathname === "/settings"}>
                <Settings className="w-[18px] h-[18px]" />
            </GuardedLink>
            {showAccount && (
                <button
                    className={linkClass(false)}
                    title="Выйти"
                    onClick={() => setLogoutOpen(true)}
                >
                    <LogOut className="w-[18px] h-[18px]" />
                </button>
            )}
            <ConfirmDialog
                open={logoutOpen}
                title="Выйти из аккаунта?"
                message="Несохранённые изменения будут потеряны. Сохранённые сценарии останутся на месте."
                confirmLabel="Выйти"
                onCancel={() => setLogoutOpen(false)}
                onConfirm={async () => {
                    setLogoutOpen(false);
                    await logout();
                    navigate("/");
                }}
            />
            <TutorialModal
                open={tutorialOpen}
                mode="tour"
                onClose={() => setTutorialOpen(false)}
                onStartInteractive={() => {
                    setTutorialOpen(false);
                    go("/workflow/new?tour=1");
                }}
            />
        </aside>
    );
}
