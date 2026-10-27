import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import { Alert, Badge, Button, Card, Select, Spinner } from "../../components/common/ui";
import { formatDate, formatDateTime, formatRub } from "../../i18n";
import type { Period } from "../../types/app";

export default function AdminUsers() {
    const { t } = useTranslation();
    const [query, setQuery] = useState("");
    const [offset, setOffset] = useState(0);
    const [data, setData] = useState<{ total: number; items: any[] } | null>(null);
    const [selected, setSelected] = useState<number | null>(null);

    useEffect(() => {
        const timer = setTimeout(() => api.adminUsers(query, offset).then(({ data: d }) => setData(d)), 250);
        return () => clearTimeout(timer);
    }, [query, offset, selected]);

    return (
        <div className="space-y-4">
            <input value={query} onChange={(e) => { setQuery(e.target.value); setOffset(0); }} placeholder={t("admin.users.search")}
                className="w-full max-w-sm px-3 py-2 border border-gray-300 rounded-lg text-sm" />
            {!data ? <Spinner /> : (
                <Card className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-gray-500 border-b border-gray-100">
                                {["user", "plan", "registered", "lastLogin", "status"].map((c) => <th key={c} className="px-4 py-3 font-medium">{t(`admin.users.cols.${c}`)}</th>)}
                            </tr>
                        </thead>
                        <tbody>
                            {data.items.map((u) => (
                                <tr key={u.id} onClick={() => setSelected(u.id)} className="border-b border-gray-50 last:border-0 hover:bg-gray-50 cursor-pointer">
                                    <td className="px-4 py-3"><div className="font-medium">{u.email}</div><div className="text-xs text-gray-400">{u.name}</div></td>
                                    <td className="px-4 py-3"><Badge color={u.plan === "free" ? "gray" : "blue"}>{u.plan}</Badge> {u.role === "admin" && <Badge color="indigo">admin</Badge>}</td>
                                    <td className="px-4 py-3 text-gray-500">{formatDate(u.created_at)}</td>
                                    <td className="px-4 py-3 text-gray-500">{formatDateTime(u.last_login_at)}</td>
                                    <td className="px-4 py-3">{u.is_active ? <Badge color="green">{t("admin.users.active")}</Badge> : <Badge color="red">{t("admin.users.blocked")}</Badge>}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <div className="flex items-center justify-between px-4 py-3 text-xs text-gray-500">
                        <span>{t("admin.users.total", { n: data.total })}</span>
                        <div className="flex gap-2">
                            <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>←</Button>
                            <Button size="sm" variant="secondary" disabled={offset + 25 >= data.total} onClick={() => setOffset(offset + 25)}>→</Button>
                        </div>
                    </div>
                </Card>
            )}
            {selected !== null && <UserDrawer id={selected} onClose={() => setSelected(null)} />}
        </div>
    );
}

function UserDrawer({ id, onClose }: { id: number; onClose: () => void }) {
    const { t } = useTranslation();
    const [detail, setDetail] = useState<any>(null);
    const [grant, setGrant] = useState<{ plan_code: string; period: Period }>({ plan_code: "pro", period: "month" });
    const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

    const load = () => api.adminUser(id).then(({ data }) => setDetail(data));
    useEffect(() => { void load(); }, [id]);

    const patch = async (body: Record<string, any>) => {
        const { error } = await api.adminPatchUser(id, body);
        setMsg(error ? { type: "error", text: error } : { type: "success", text: t("admin.users.saved") });
        await load();
    };
    const doGrant = async () => {
        const { error } = await api.adminGrant(id, grant);
        setMsg(error ? { type: "error", text: error } : { type: "success", text: t("admin.users.granted") });
        await load();
    };

    return (
        <div className="fixed inset-0 z-30 flex justify-end bg-black/30" onClick={onClose}>
            <div className="w-full max-w-lg bg-white h-full overflow-y-auto p-6 space-y-5" onClick={(e) => e.stopPropagation()}>
                {!detail ? <Spinner /> : (
                    <>
                        <div className="flex items-start justify-between">
                            <div>
                                <h2 className="text-lg font-bold">{detail.user.email}</h2>
                                <p className="text-sm text-gray-500">{detail.user.name || "—"} · {t("admin.users.since", { date: formatDate(detail.user.created_at) })}</p>
                            </div>
                            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
                        </div>
                        {msg && <Alert type={msg.type}>{msg.text}</Alert>}

                        <div className="flex gap-2">
                            <Button size="sm" variant={detail.user.is_active ? "danger" : "success"} onClick={() => patch({ is_active: !detail.user.is_active })}>
                                {detail.user.is_active ? t("admin.users.block") : t("admin.users.unblock")}
                            </Button>
                            <Button size="sm" variant="secondary" onClick={() => patch({ role: detail.user.role === "admin" ? "user" : "admin" })}>
                                {detail.user.role === "admin" ? t("admin.users.demote") : t("admin.users.promote")}
                            </Button>
                        </div>

                        <section>
                            <h3 className="font-semibold mb-2">{t("admin.users.subscription")}</h3>
                            <p className="text-sm text-gray-600">
                                {detail.plan.name}{detail.subscription.period ? ` · ${detail.subscription.period}` : ""}
                                {detail.subscription.current_period_end && ` · ${t("admin.users.until")} ${formatDate(detail.subscription.current_period_end)}`}
                            </p>
                            <div className="mt-3 flex items-end gap-2">
                                <Select label={t("admin.users.grantPlan")} value={grant.plan_code} onChange={(e) => setGrant({ ...grant, plan_code: e.target.value })}>
                                    <option value="free">Free</option><option value="pro">Pro</option><option value="business">Business</option>
                                </Select>
                                <Select label={t("admin.users.grantPeriod")} value={grant.period} onChange={(e) => setGrant({ ...grant, period: e.target.value as Period })}>
                                    <option value="month">{t("checkout.month")}</option><option value="year">{t("checkout.year")}</option>
                                </Select>
                                <Button size="md" onClick={doGrant}>{t("admin.users.grant")}</Button>
                            </div>
                        </section>

                        <section>
                            <h3 className="font-semibold mb-2">{t("admin.users.usage")}</h3>
                            <p className="text-sm text-gray-600">
                                AI: {detail.usage.ai_run} · {t("admin.stats.regular")}: {detail.usage.regular_run} · {t("pricing.rows.aiChat")}: {detail.usage.ai_chat}
                            </p>
                            <p className="text-sm text-gray-600 mt-1">
                                {t("admin.users.workflowsCount", { ai: detail.workflows_count.ai_workflows, regular: detail.workflows_count.regular_workflows })}
                            </p>
                        </section>

                        <section>
                            <h3 className="font-semibold mb-2">{t("admin.users.payments")}</h3>
                            {detail.payments.length === 0 ? <p className="text-sm text-gray-400">—</p> : (
                                <ul className="text-sm space-y-1">
                                    {detail.payments.map((p: any) => (
                                        <li key={p.id} className="flex justify-between"><span>{formatDateTime(p.created_at)} · {p.plan_code}</span><span>{formatRub(p.amount)} · {p.status}</span></li>
                                    ))}
                                </ul>
                            )}
                        </section>
                    </>
                )}
            </div>
        </div>
    );
}
