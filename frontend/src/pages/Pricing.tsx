import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useAuth } from "../store/auth";
import type { Plan } from "../types/app";
import PricingCards from "../components/billing/PricingCards";
import PublicHeader from "../components/PublicHeader";
import { Spinner } from "../components/common/ui";

export function usePlanSelection() {
    const navigate = useNavigate();
    const me = useAuth((s) => s.me);
    return (plan: Plan, period: "month" | "year") => {
        const query = `plan=${plan.code}&period=${period}`;
        navigate(me ? `/checkout?${query}` : `/register?${query}`);
    };
}

export default function Pricing() {
    const { t } = useTranslation();
    const [plans, setPlans] = useState<Plan[] | null>(null);
    const me = useAuth((s) => s.me);
    const select = usePlanSelection();

    useEffect(() => {
        api.getPlans().then(({ data }) => setPlans(data ?? []));
    }, []);

    return (
        <div className="min-h-screen bg-gray-50">
            <PublicHeader />
            <main className="max-w-6xl mx-auto px-6 py-14">
                <div className="text-center max-w-2xl mx-auto">
                    <h1 className="text-3xl sm:text-4xl font-extrabold text-gray-900">{t("pricing.title")}</h1>
                    <p className="mt-3 text-gray-500">{t("pricing.subtitle")}</p>
                </div>

                {!plans ? (
                    <Spinner />
                ) : (
                    <>
                        <div className="mt-12">
                            <PricingCards plans={plans} current={me?.subscription} onSelect={select} />
                        </div>
                        <p className="mt-8 text-center text-xs text-gray-400">{t("pricing.note")}</p>
                    </>
                )}
            </main>
        </div>
    );
}
