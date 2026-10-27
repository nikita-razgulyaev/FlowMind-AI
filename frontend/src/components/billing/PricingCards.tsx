import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import type { Period, Plan, Subscription } from "../../types/app";
import { formatRub } from "../../i18n";
import { Badge, Button } from "../common/ui";

interface Props {
    plans: Plan[];
    current?: Subscription | null;           // у гостя нет подписки
    onSelect: (plan: Plan, period: Period) => void;
    defaultPeriod?: Period;
}

/** Карточки тарифов; у каждой карточки свой переключатель «Месяц / Год» и динамическая цена. */
export default function PricingCards({ plans, current, onSelect, defaultPeriod = "year" }: Props) {
    const { t } = useTranslation();
    const [periods, setPeriods] = useState<Record<string, Period>>({});
    const periodOf = (code: string): Period => periods[code] ?? defaultPeriod;

    return (
        <div className="grid gap-6 md:grid-cols-3">
            {plans.map((plan) => {
                const period = periodOf(plan.code);
                const isFree = plan.price_month === 0;
                const perMonth = period === "month" ? plan.price_month : Math.round(plan.price_year / 12);
                const yearSaving = plan.price_month * 12 - plan.price_year;
                const popular = plan.code === "pro";
                const isCurrent = !!current && current.effective_plan === plan.code && (isFree || current.period === period);

                return (
                    <div
                        key={plan.code}
                        className={`relative flex flex-col bg-white rounded-2xl border p-6 shadow-sm ${
                            popular ? "border-blue-500 ring-2 ring-blue-100" : "border-gray-200"
                        }`}
                    >
                        {popular && (
                            <span className="absolute -top-3 left-1/2 -translate-x-1/2">
                                <Badge color="blue">{t("pricing.popular")}</Badge>
                            </span>
                        )}
                        <h3 className="text-lg font-bold text-gray-900">{plan.name}</h3>
                        <p className="text-sm text-gray-500 mt-1 min-h-[2.5rem]">{plan.description}</p>

                        <div className="inline-flex self-start mt-4 p-0.5 bg-gray-100 rounded-lg text-xs font-medium" role="group" aria-label={t("pricing.billingPeriod")}>
                            {(["month", "year"] as Period[]).map((p) => (
                                <button
                                    key={p}
                                    type="button"
                                    onClick={() => setPeriods({ ...periods, [plan.code]: p })}
                                    className={`px-3 py-1 rounded-md transition-colors ${
                                        period === p ? "bg-white shadow text-gray-900" : "text-gray-500 hover:text-gray-700"
                                    }`}
                                >
                                    {t(p === "month" ? "pricing.monthly" : "pricing.yearly")}
                                    {p === "year" && !isFree && <span className="ml-1 text-emerald-600">−20%</span>}
                                </button>
                            ))}
                        </div>

                        <div className="mt-4">
                            <div className="flex items-baseline gap-1">
                                <span className="text-4xl font-extrabold text-gray-900 tabular-nums">{formatRub(perMonth)}</span>
                                <span className="text-sm text-gray-500">/ {t("pricing.perMonth")}</span>
                            </div>
                            <p className="text-xs text-gray-400 mt-1 h-4">
                                {isFree
                                    ? t("pricing.forever")
                                    : period === "year"
                                      ? t("pricing.billedYearly", { total: formatRub(plan.price_year), saving: formatRub(yearSaving) })
                                      : t("pricing.billedMonthly")}
                            </p>
                        </div>

                        <ul className="mt-5 space-y-2 flex-1">
                            {plan.features.map((feature) => (
                                <li key={feature} className="flex gap-2 text-sm text-gray-700">
                                    <Check className="w-4 h-4 mt-0.5 shrink-0 text-emerald-500" />
                                    {feature}
                                </li>
                            ))}
                        </ul>

                        <Button
                            className="mt-6 w-full"
                            variant={popular ? "primary" : "secondary"}
                            disabled={isCurrent}
                            onClick={() => onSelect(plan, period)}
                        >
                            {isCurrent ? t("pricing.currentPlan") : current ? (isFree ? t("pricing.switchToFree") : t("pricing.choose")) : isFree ? t("pricing.startFree") : t("pricing.tryPlan", { plan: plan.name })}
                        </Button>
                    </div>
                );
            })}
        </div>
    );
}
