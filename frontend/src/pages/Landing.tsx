import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot, CalendarPlus, Cloud, HardDrive, MessageCircle, Send, Sparkles, Table, Workflow } from "lucide-react";
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

function FlowIllustration() {
    const box = "absolute w-40 rounded-xl border-2 bg-white shadow-md px-3 py-2 flex items-center gap-2 text-sm font-semibold";
    return (
        <div className="relative w-full max-w-xl h-72 mx-auto" aria-hidden="true">
            <svg className="absolute inset-0 w-full h-full" viewBox="0 0 560 288" fill="none">
                <path d="M170 56 C 200 56, 190 110, 220 110" stroke="#3b82f6" strokeWidth="2" />
                <path d="M380 110 C 410 110, 400 56, 430 56" stroke="#3b82f6" strokeWidth="2" />
                <path d="M300 140 C 300 175, 300 190, 300 220" stroke="#6366f1" strokeWidth="2" strokeDasharray="5 4" />
            </svg>
            <div className={`${box} border-cyan-200 left-0 top-4`}><span className="w-7 h-7 rounded-lg bg-cyan-100 text-cyan-700 flex items-center justify-center"><MessageCircle className="w-4 h-4" /></span>Telegram</div>
            <div className={`${box} border-indigo-300 left-[40%] top-[76px]`}><span className="w-7 h-7 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center"><Bot className="w-4 h-4" /></span>AI-агент</div>
            <div className={`${box} border-sky-200 right-0 top-4`}><span className="w-7 h-7 rounded-lg bg-sky-100 text-sky-700 flex items-center justify-center"><Send className="w-4 h-4" /></span>Ответ</div>
            <div className={`${box} border-green-200 left-[40%] top-[220px]`}><span className="w-7 h-7 rounded-lg bg-green-100 text-green-700 flex items-center justify-center"><Table className="w-4 h-4" /></span>Sheets</div>
            <div className={`${box} border-red-200 left-0 top-[220px]`}><span className="w-7 h-7 rounded-lg bg-red-100 text-red-700 flex items-center justify-center"><CalendarPlus className="w-4 h-4" /></span>Calendar</div>
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
                        {!me && <p className="mt-4 text-xs text-gray-400">{t("landing.noCard")}</p>}
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

            <section className="bg-gray-50">
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
