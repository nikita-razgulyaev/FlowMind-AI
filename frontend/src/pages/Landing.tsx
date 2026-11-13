import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot, Cloud, HardDrive, MessageCircle, Sparkles, Table, Workflow } from "lucide-react";
import { NODE_META } from "../components/canvas/CanvasNode";
import { api } from "../api/client";
import { useAuth } from "../store/auth";
import type { Plan } from "../types/app";
import PricingCards from "../components/billing/PricingCards";
import PublicHeader from "../components/PublicHeader";
import { Button } from "../components/common/ui";
import { usePlanSelection } from "./Pricing";

const FEATURES = [
    { key: "editor", icon: Workflow, color: "bg-blue-100 text-blue-600" },
    { key: "agents", icon: Bot, color: "bg-indigo-100 text-indigo-600" },
    { key: "telegram", icon: MessageCircle, color: "bg-cyan-100 text-cyan-600" },
    { key: "chat", icon: Sparkles, color: "bg-purple-100 text-purple-600" },
    { key: "google", icon: Table, color: "bg-emerald-100 text-emerald-600" },
    { key: "models", icon: Cloud, color: "bg-orange-100 text-orange-600" },
] as const;

const FAQ_KEYS = ["free", "ownKeys", "local", "payment", "cancel"] as const;

const SCHEME_W = 576;
const SCHEME_H = 288;
const NODE_H = 44;

/** Схема: Почта → ИИ-агент → три ветки: нейросеть → отправить письмо, таблица, календарь. Масштабируется под ширину экрана. */
function FlowIllustration() {
    const wrapRef = useRef<HTMLDivElement>(null);
    const [scale, setScale] = useState(1);
    useLayoutEffect(() => {
        const update = () => setScale(Math.min(1, (wrapRef.current?.clientWidth ?? SCHEME_W) / SCHEME_W));
        update();
        window.addEventListener("resize", update);
        return () => window.removeEventListener("resize", update);
    }, []);

    const node = (type: string, name: string, x: number, y: number, w: number) => {
        const meta = NODE_META[type];
        const Icon = meta.icon;
        return (
            <div
                key={name}
                className={`absolute flex items-center gap-2 rounded-xl border-2 bg-white px-3 shadow-md min-w-0 overflow-hidden ${meta.ring}`}
                style={{ left: x, top: y, width: w, height: NODE_H }}
            >
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${meta.badge}`}>
                    <Icon className="h-4 w-4" />
                </span>
                <span className="truncate text-[13px] font-semibold" title={name}>{name}</span>
            </div>
        );
    };
    const line = (d: string) => <path key={d} d={d} stroke="#3b82f6" strokeWidth="2" fill="none" />;

    return (
        <div ref={wrapRef} className="mx-auto w-full max-w-xl" style={{ height: SCHEME_H * scale }} aria-hidden="true">
            <div className="relative origin-top-left" style={{ width: SCHEME_W, height: SCHEME_H, transform: `scale(${scale})` }}>
                <svg className="absolute inset-0" width={SCHEME_W} height={SCHEME_H} viewBox={`0 0 ${SCHEME_W} ${SCHEME_H}`}>
                    {line("M118 144 H150")}
                    {line("M268 144 C 290 144, 280 50, 304 50")}
                    {line("M268 144 H304")}
                    {line("M268 144 C 290 144, 280 238, 304 238")}
                    {line("M422 50 H442")}
                </svg>
                {node("email_trigger", "Почта", 0, 122, 118)}
                {node("agent", "ИИ-агент", 150, 122, 118)}
                {node("llm", "Нейросеть", 304, 28, 118)}
                {node("email_send", "Отправить письмо", 442, 28, 134)}
                {node("google_sheets_append", "Таблица", 304, 122, 118)}
                {node("google_calendar_create_event", "Календарь", 304, 216, 118)}
            </div>
        </div>
    );
}

export default function Landing() {
    const { t } = useTranslation();
    const [plans, setPlans] = useState<Plan[]>([]);
    const me = useAuth((st) => st.me);
    const select = usePlanSelection();
    useEffect(() => { api.getPlans().then(({ data }) => setPlans(data ?? [])); }, []);

    return (
        <div className="bg-white text-gray-900">
            <PublicHeader />

            <section className="bg-gradient-to-b from-slate-50 via-blue-50/60 to-white">
                <div className="max-w-6xl mx-auto px-6 pt-16 pb-20 grid lg:grid-cols-2 gap-12 items-center">
                    <div>
                        <span className="inline-block text-xs font-semibold tracking-wide uppercase text-blue-700 bg-blue-100 rounded-full px-3 py-1">{t("landing.badge")}</span>
                        <h1 className="mt-5 text-4xl sm:text-5xl font-extrabold leading-tight">{t("landing.heroTitle")}</h1>
                        <p className="mt-5 text-lg text-gray-600 max-w-xl">{t("landing.heroText")}</p>
                        <div className="mt-8 flex flex-wrap gap-3">
                            <Link to={me ? "/" : "/register"}>
                                <Button size="lg">{me ? t("landing.openApp") : t("landing.startFree")}</Button>
                            </Link>
                            <Link to="/about#pricing"><Button size="lg" variant="secondary">{t("landing.seePricing")}</Button></Link>
                        </div>
                    </div>
                    <FlowIllustration />
                </div>
            </section>

            <section id="features" className="scroll-mt-20 max-w-6xl mx-auto px-6 py-20">
                <h2 className="text-3xl font-extrabold text-center">{t("landing.featuresTitle")}</h2>
                <div className="mt-12 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
                    {FEATURES.map(({ key, icon: Icon, color }) => (
                        <div key={key} className="rounded-2xl border border-gray-200 p-6 hover:shadow-md transition-shadow">
                            <span className={`w-10 h-10 rounded-xl flex items-center justify-center ${color}`}><Icon className="w-5 h-5" /></span>
                            <h3 className="mt-4 font-semibold text-lg">{t(`landing.features.${key}.title`)}</h3>
                            <p className="mt-2 text-sm text-gray-600">{t(`landing.features.${key}.text`)}</p>
                        </div>
                    ))}
                </div>
            </section>

            <section id="how" className="scroll-mt-20 bg-gray-50">
                <div className="max-w-6xl mx-auto px-6 py-20">
                    <h2 className="text-3xl font-extrabold text-center">{t("landing.howTitle")}</h2>
                    <ol className="mt-12 grid md:grid-cols-3 gap-8">
                        {[1, 2, 3].map((n) => (
                            <li key={n} className="relative bg-white rounded-2xl border border-gray-200 p-6">
                                <span className="w-9 h-9 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center">{n}</span>
                                <h3 className="mt-4 font-semibold">{t(`landing.steps.${n}.title`)}</h3>
                                <p className="mt-2 text-sm text-gray-600">{t(`landing.steps.${n}.text`)}</p>
                            </li>
                        ))}
                    </ol>
                </div>
            </section>

            <section className="max-w-6xl mx-auto px-6 py-20">
                <h2 className="text-3xl font-extrabold text-center">{t("landing.deployTitle")}</h2>
                <p className="mt-3 text-center text-gray-500 max-w-2xl mx-auto">{t("landing.deployText")}</p>
                <div className="mt-12 grid md:grid-cols-2 gap-6">
                    <div className="rounded-2xl border border-gray-200 p-6">
                        <Cloud className="w-7 h-7 text-blue-600" />
                        <h3 className="mt-3 font-semibold text-lg">{t("landing.cloud.title")}</h3>
                        <p className="mt-2 text-sm text-gray-600">{t("landing.cloud.text")}</p>
                    </div>
                    <div className="rounded-2xl border border-gray-200 p-6">
                        <HardDrive className="w-7 h-7 text-emerald-600" />
                        <h3 className="mt-3 font-semibold text-lg">{t("landing.local.title")}</h3>
                        <p className="mt-2 text-sm text-gray-600">{t("landing.local.text")}</p>
                        <pre className="mt-4 text-xs bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto">docker compose up --build</pre>
                    </div>
                </div>
            </section>

            <section id="pricing" className="scroll-mt-20 bg-gray-50">
                <div className="max-w-6xl mx-auto px-6 py-20">
                    <h2 className="text-3xl font-extrabold text-center">{t("pricing.title")}</h2>
                    <p className="mt-3 text-center text-gray-500">{t("pricing.subtitle")}</p>
                    <div className="mt-12"><PricingCards plans={plans} onSelect={select} /></div>
                </div>
            </section>

            <section id="faq" className="scroll-mt-20 max-w-3xl mx-auto px-6 py-20">
                <h2 className="text-3xl font-extrabold text-center">{t("landing.faqTitle")}</h2>
                <div className="mt-10 divide-y divide-gray-200 border-y border-gray-200">
                    {FAQ_KEYS.map((key) => (
                        <details key={key} className="group py-4">
                            <summary className="cursor-pointer font-medium list-none flex justify-between items-center">
                                {t(`landing.faq.${key}.q`)}
                                <span className="text-gray-400 group-open:rotate-45 transition-transform text-xl leading-none">+</span>
                            </summary>
                            <p className="mt-3 text-sm text-gray-600">{t(`landing.faq.${key}.a`)}</p>
                        </details>
                    ))}
                </div>
            </section>

            <section className="bg-blue-600">
                <div className="max-w-4xl mx-auto px-6 py-16 text-center text-white">
                    <h2 className="text-3xl font-extrabold">{t("landing.ctaTitle")}</h2>
                    <p className="mt-3 text-blue-100">{t("landing.ctaText")}</p>
                    <Link to={me ? "/" : "/register"}>
                        <Button size="lg" variant="secondary" className="mt-8">{me ? t("landing.openApp") : t("landing.startFree")}</Button>
                    </Link>
                </div>
            </section>

            <footer className="border-t border-gray-100">
                <div className="max-w-6xl mx-auto px-6 py-8 flex flex-wrap items-center justify-between gap-4 text-sm text-gray-500">
                    <span>© {new Date().getFullYear()} FlowMind AI</span>
                    <nav className="flex flex-wrap gap-x-6 gap-y-2">
                        <Link to="/about#features" className="hover:text-gray-700">{t("landing.navFeatures")}</Link>
                        <Link to="/pricing" className="hover:text-gray-700">{t("landing.navPricing")}</Link>
                        <Link to="/about#faq" className="hover:text-gray-700">{t("landing.navFaq")}</Link>
                        {me ? (
                            <Link to="/" className="hover:text-gray-700">{t("landing.openApp")}</Link>
                        ) : (
                            <>
                                <Link to="/login" className="hover:text-gray-700">{t("auth.login")}</Link>
                                <Link to="/register" className="hover:text-gray-700">{t("auth.register")}</Link>
                            </>
                        )}
                    </nav>
                </div>
            </footer>
        </div>
    );
}
