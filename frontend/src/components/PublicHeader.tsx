import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Menu, Workflow, X } from "lucide-react";
import { useAuth } from "../store/auth";
import { Button } from "./common/ui";

/** Шапка «презентационных» страниц (лендинг, тарифы). Ссылки с якорями ведут на /about — страницу, доступную всем. */
export default function PublicHeader() {
    const { t } = useTranslation();
    const { me, config } = useAuth();
    const { pathname } = useLocation();
    const [open, setOpen] = useState(false);
    const authRequired = !!config?.auth_required;

    useEffect(() => setOpen(false), [pathname]);

    const nav: { to: string; label: string; active: boolean }[] = [
        { to: "/about#features", label: t("landing.navFeatures"), active: false },
        { to: "/pricing", label: t("landing.navPricing"), active: pathname === "/pricing" },
        { to: "/about#faq", label: t("landing.navFaq"), active: false },
    ];
    if (me && authRequired) nav.push({ to: "/account", label: t("nav.account"), active: false });

    const linkClass = (active: boolean) =>
        `text-sm transition-colors ${active ? "text-blue-600 font-medium" : "text-gray-600 hover:text-gray-900"}`;

    const actions = me ? (
        <Link to="/"><Button size="sm">{t("landing.openApp")}</Button></Link>
    ) : (
        <>
            <Link to="/login"><Button size="sm" variant="ghost">{t("auth.login")}</Button></Link>
            <Link to="/register"><Button size="sm">{t("landing.startFree")}</Button></Link>
        </>
    );

    return (
        <header className="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-gray-100">
            <div className="max-w-6xl mx-auto px-6 h-16 flex items-center gap-8">
                <Link to="/" className="flex items-center gap-2 font-bold text-gray-900">
                    <span className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center">
                        <Workflow className="w-4 h-4" />
                    </span>
                    FlowMind AI
                </Link>
                <nav className="hidden md:flex gap-6">
                    {nav.map((item) => (
                        <Link key={item.to} to={item.to} className={linkClass(item.active)} aria-current={item.active ? "page" : undefined}>
                            {item.label}
                        </Link>
                    ))}
                </nav>
                <div className="ml-auto hidden md:flex items-center gap-2">{actions}</div>
                <button
                    className="ml-auto md:hidden p-2 -mr-2 text-gray-600"
                    onClick={() => setOpen((v) => !v)}
                    aria-label={open ? t("nav.closeMenu") : t("nav.menu")}
                    aria-expanded={open}
                >
                    {open ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
                </button>
            </div>
            {open && (
                <div className="md:hidden border-t border-gray-100 bg-white px-6 py-4 space-y-4">
                    <nav className="flex flex-col gap-3">
                        {nav.map((item) => (
                            <Link key={item.to} to={item.to} className={linkClass(item.active)}>{item.label}</Link>
                        ))}
                    </nav>
                    <div className="flex gap-2">{actions}</div>
                </div>
            )}
        </header>
    );
}
