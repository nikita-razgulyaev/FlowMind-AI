import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { Plan, PlanLimits } from "../../types/app";
import { Alert, Button, Card, Field, Spinner } from "../../components/common/ui";

const LIMIT_KEYS: (keyof PlanLimits)[] = ["ai_workflows", "regular_workflows", "ai_run", "regular_run", "telegram_triggers", "ai_chat", "history_days"];

function PlanEditor({ plan, onSaved }: { plan: Plan; onSaved: () => void }) {
    const { t } = useTranslation();
    const [name, setName] = useState(plan.name);
    const [priceMonth, setPriceMonth] = useState(String(plan.price_month / 100));
    const [priceYear, setPriceYear] = useState(String(plan.price_year / 100));
    const [features, setFeatures] = useState(plan.features.join("\n"));
    // пустая строка = «без ограничений»
    const [limits, setLimits] = useState<Record<string, string>>(
        Object.fromEntries(LIMIT_KEYS.map((k) => [k, plan.limits[k] === null ? "" : String(plan.limits[k])])),
    );
    const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

    const save = async () => {
        const { error } = await api.adminUpdatePlan(plan.code, {
            name,
            price_month: Math.round(Number(priceMonth) * 100),
            price_year: Math.round(Number(priceYear) * 100),
            features: features.split("\n").map((s) => s.trim()).filter(Boolean),
            limits: Object.fromEntries(LIMIT_KEYS.map((k) => [k, limits[k].trim() === "" ? null : Number(limits[k])])),
        });
        setMsg(error ? { type: "error", text: error } : { type: "success", text: t("admin.plans.saved") });
        if (!error) onSaved();
    };

    return (
        <Card className="p-5 space-y-4">
            <div className="flex items-center justify-between">
                <h3 className="font-semibold text-lg">{plan.code}</h3>
                <Button size="sm" onClick={save}>{t("account.save")}</Button>
            </div>
            <div className="grid grid-cols-3 gap-3">
                <Field label={t("admin.plans.name")} value={name} onChange={(e) => setName(e.target.value)} />
                <Field label={t("admin.plans.priceMonth")} type="number" min={0} value={priceMonth} onChange={(e) => setPriceMonth(e.target.value)} />
                <Field label={t("admin.plans.priceYear")} type="number" min={0} value={priceYear} onChange={(e) => setPriceYear(e.target.value)} />
            </div>
            <div>
                <p className="text-sm font-medium text-gray-700 mb-1">{t("admin.plans.limits")}</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {LIMIT_KEYS.map((k) => (
                        <Field key={k} label={t(`admin.plans.limit.${k}`)} type="number" min={0} placeholder="∞" value={limits[k]} onChange={(e) => setLimits({ ...limits, [k]: e.target.value })} />
                    ))}
                </div>
                <p className="text-xs text-gray-400 mt-1">{t("admin.plans.limitHint")}</p>
            </div>
            <label className="block">
                <span className="block text-sm font-medium text-gray-700 mb-1">{t("admin.plans.features")}</span>
                <textarea rows={5} value={features} onChange={(e) => setFeatures(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
            </label>
            {msg && <Alert type={msg.type}>{msg.text}</Alert>}
        </Card>
    );
}

export default function AdminPlans() {
    const { t } = useTranslation();
    const [plans, setPlans] = useState<Plan[] | null>(null);
    const load = () => api.adminPlans().then(({ data }) => setPlans(data ?? []));
    useEffect(() => { void load(); }, []);
    if (!plans) return <Spinner />;
    return (
        <div className="space-y-5">
            <Alert type="info">{t("admin.plans.info")}</Alert>
            {plans.filter((p) => p.code !== "local").map((p) => <PlanEditor key={p.code} plan={p} onSaved={load} />)}
        </div>
    );
}
