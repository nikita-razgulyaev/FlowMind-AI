import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import { Badge, Card, Spinner } from "../../components/common/ui";
import { formatRub } from "../../i18n";

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
    return (
        <Card className="p-5">
            <p className="text-xs text-gray-400">{label}</p>
            <p className="text-2xl font-extrabold mt-1 tabular-nums">{value}</p>
            {hint && <p className="text-xs text-gray-400 mt-1">{hint}</p>}
        </Card>
    );
}

export default function AdminDashboard() {
    const { t } = useTranslation();
    const [stats, setStats] = useState<any>(null);
    useEffect(() => { api.adminStats().then(({ data }) => setStats(data)); }, []);
    if (!stats) return <Spinner />;

    const days: { date: string; ai: number; regular: number }[] = stats.runs_by_day;
    const max = Math.max(1, ...days.map((d) => d.ai + d.regular));
    const aiPercent = stats.ai.daily_cap ? Math.min(100, Math.round((stats.ai.calls_today / stats.ai.daily_cap) * 100)) : 0;

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <Stat label={t("admin.stats.users")} value={stats.users_total} hint={t("admin.stats.newWeek", { n: stats.users_new_7d })} />
                <Stat label={t("admin.stats.paid")} value={stats.paid_subscriptions.pro + stats.paid_subscriptions.business}
                    hint={`Про: ${stats.paid_subscriptions.pro} · Бизнес: ${stats.paid_subscriptions.business}`} />
                <Stat label={t("admin.stats.mrr")} value={formatRub(stats.mrr)} hint={t("admin.stats.mrrHint")} />
                <Stat label={t("admin.stats.revenue30")} value={formatRub(stats.revenue_30d)} hint={t("admin.stats.revenueTotal", { total: formatRub(stats.revenue_total) })} />
                <Stat label={t("admin.stats.workflows")} value={stats.workflows_total} />
                <Stat label={t("admin.stats.executions")} value={stats.executions_total} />
            </div>

            <Card className="p-5">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="font-semibold">{t("admin.stats.runsByDay")}</h2>
                    <div className="flex gap-3 text-xs text-gray-500">
                        <span className="flex items-center gap-1"><i className="w-2.5 h-2.5 rounded-sm bg-indigo-500 inline-block" /> AI</span>
                        <span className="flex items-center gap-1"><i className="w-2.5 h-2.5 rounded-sm bg-blue-300 inline-block" /> {t("admin.stats.regular")}</span>
                    </div>
                </div>
                <div className="flex items-end gap-2 h-40">
                    {days.map((d) => (
                        <div key={d.date} className="flex-1 flex flex-col justify-end h-full group relative" title={`${d.date}: AI ${d.ai}, ${d.regular}`}>
                            <div className="bg-indigo-500 rounded-t-sm" style={{ height: `${(d.ai / max) * 100}%` }} />
                            <div className="bg-blue-300" style={{ height: `${(d.regular / max) * 100}%` }} />
                            <span className="text-[10px] text-gray-400 text-center mt-1">{d.date.slice(8)}</span>
                        </div>
                    ))}
                </div>
            </Card>

            <Card className="p-5">
                <div className="flex items-center gap-2 mb-3">
                    <h2 className="font-semibold">{t("admin.stats.aiKey")}</h2>
                    <Badge color={stats.ai.enabled ? "green" : "red"}>{stats.ai.enabled ? t("admin.stats.aiOn") : t("admin.stats.aiOff")}</Badge>
                    {!stats.ai.key_configured && <Badge color="amber">{t("admin.stats.noKey")}</Badge>}
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div className={`h-full ${aiPercent > 85 ? "bg-red-500" : "bg-blue-500"}`} style={{ width: `${aiPercent}%` }} />
                </div>
                <p className="text-xs text-gray-500 mt-2">{t("admin.stats.aiCalls", { used: stats.ai.calls_today, cap: stats.ai.daily_cap })}</p>
            </Card>
        </div>
    );
}
