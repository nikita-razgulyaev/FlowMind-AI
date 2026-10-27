import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useAuth } from "../store/auth";
import type { Payment } from "../types/app";
import AppLayout from "../components/AppLayout";
import { Alert, Badge, Button, Card, Field, Spinner, UsageBar } from "../components/common/ui";
import { formatDate, formatDateTime, formatRub } from "../i18n";

const TABS = ["profile", "subscription", "payments", "usage"] as const;
type Tab = (typeof TABS)[number];

const PAYMENT_BADGE: Record<string, "green" | "amber" | "red" | "gray"> = {
    succeeded: "green", pending: "amber", requires_action: "amber", failed: "red", canceled: "gray",
};

export default function Account() {
    const { t } = useTranslation();
    const [params, setParams] = useSearchParams();
    const me = useAuth((s) => s.me);
    const tab = (TABS.includes(params.get("tab") as Tab) ? params.get("tab") : "profile") as Tab;

    if (!me) return <AppLayout><Spinner /></AppLayout>;
    return (
        <AppLayout>
            <h1 className="text-2xl font-bold text-gray-900">{t("account.title")}</h1>
            <p className="text-sm text-gray-500 mt-1">{me.user.email}</p>
            <div className="mt-6 flex gap-1 border-b border-gray-200">
                {TABS.map((id) => (
                    <button key={id} onClick={() => setParams({ tab: id })}
                        className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 ${tab === id ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"}`}>
                        {t(`account.tabs.${id}`)}
                    </button>
                ))}
            </div>
            <div className="mt-6">
                {tab === "profile" && <ProfileTab />}
                {tab === "subscription" && <SubscriptionTab />}
                {tab === "payments" && <PaymentsTab />}
                {tab === "usage" && <UsageTab />}
            </div>
        </AppLayout>
    );
}

function ProfileTab() {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { me, loadMe, logout } = useAuth();
    const [name, setName] = useState(me?.user.name ?? "");
    const [profileMsg, setProfileMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
    const [pw, setPw] = useState({ current: "", next: "" });
    const [pwMsg, setPwMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
    const [deletePw, setDeletePw] = useState("");
    const [deleteErr, setDeleteErr] = useState<string | null>(null);
    const [confirmDelete, setConfirmDelete] = useState(false);

    const saveProfile = async (e: FormEvent) => {
        e.preventDefault();
        const { error } = await api.updateProfile(name);
        if (error) return setProfileMsg({ type: "error", text: error });
        await loadMe();
        setProfileMsg({ type: "success", text: t("account.saved") });
    };

    const changePassword = async (e: FormEvent) => {
        e.preventDefault();
        const { error } = await api.changePassword(pw.current, pw.next);
        if (error) return setPwMsg({ type: "error", text: error });
        setPw({ current: "", next: "" });
        setPwMsg({ type: "success", text: t("account.passwordChanged") });
    };

    const deleteAccount = async () => {
        const { error } = await api.deleteAccount(deletePw);
        if (error) return setDeleteErr(error);
        await logout();
        navigate("/");
    };

    return (
        <div className="grid md:grid-cols-2 gap-6">
            <Card className="p-6">
                <h2 className="font-semibold mb-4">{t("account.profile")}</h2>
                <form onSubmit={saveProfile} className="space-y-4">
                    <Field label={t("auth.email")} value={me?.user.email ?? ""} disabled readOnly />
                    <Field label={t("auth.name")} value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
                    {profileMsg && <Alert type={profileMsg.type}>{profileMsg.text}</Alert>}
                    <Button type="submit">{t("account.save")}</Button>
                </form>
            </Card>
            <Card className="p-6">
                <h2 className="font-semibold mb-4">{t("account.changePassword")}</h2>
                <form onSubmit={changePassword} className="space-y-4">
                    <Field label={t("account.currentPassword")} type="password" required autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
                    <Field label={t("auth.newPassword")} type="password" required minLength={8} autoComplete="new-password" hint={t("auth.passwordHint")} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
                    {pwMsg && <Alert type={pwMsg.type}>{pwMsg.text}</Alert>}
                    <Button type="submit" variant="secondary">{t("account.changePassword")}</Button>
                </form>
            </Card>
            <Card className="p-6 md:col-span-2 border-red-200">
                <h2 className="font-semibold text-red-700">{t("account.dangerZone")}</h2>
                <p className="text-sm text-gray-500 mt-1">{t("account.deleteWarning")}</p>
                {!confirmDelete ? (
                    <Button variant="danger" className="mt-4" onClick={() => setConfirmDelete(true)}>{t("account.deleteAccount")}</Button>
                ) : (
                    <div className="mt-4 max-w-sm space-y-3">
                        <Field label={t("account.confirmWithPassword")} type="password" value={deletePw} onChange={(e) => setDeletePw(e.target.value)} />
                        {deleteErr && <Alert type="error">{deleteErr}</Alert>}
                        <div className="flex gap-2">
                            <Button variant="danger" onClick={deleteAccount} disabled={!deletePw}>{t("account.deleteForever")}</Button>
                            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>{t("account.cancel")}</Button>
                        </div>
                    </div>
                )}
            </Card>
        </div>
    );
}

function SubscriptionTab() {
    const { t } = useTranslation();
    const { me, config, loadMe } = useAuth();
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
    if (!me) return null;
    const { subscription: sub, plan } = me;
    const paid = plan.code !== "free";
    const isMock = config?.payment_provider === "mock";

    const run = async (action: () => Promise<{ error?: string }>, success: string) => {
        setBusy(true);
        const { error } = await action();
        await loadMe();
        setMessage(error ? { type: "error", text: error } : { type: "success", text: success });
        setBusy(false);
    };

    return (
        <div className="space-y-6 max-w-2xl">
            <Card className="p-6">
                <div className="flex items-start justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-wide text-gray-400">{t("account.currentPlan")}</p>
                        <h2 className="text-2xl font-bold mt-1">{plan.name}</h2>
                        {sub.period && <p className="text-sm text-gray-500 mt-1">{t(sub.period === "month" ? "account.billedMonthly" : "account.billedYearly")}</p>}
                    </div>
                    <div className="flex flex-col items-end gap-1">
                        {sub.status === "past_due" && <Badge color="red">{t("account.pastDue")}</Badge>}
                        {sub.cancel_at_period_end && <Badge color="amber">{t("account.canceled")}</Badge>}
                        {sub.pending_plan_code && <Badge color="indigo">{t("account.changeScheduled")}</Badge>}
                    </div>
                </div>

                {paid && (
                    <dl className="mt-5 grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <dt className="text-gray-400">{sub.cancel_at_period_end ? t("account.accessUntil") : t("account.renewsOn")}</dt>
                            <dd className="font-medium mt-0.5">{formatDate(sub.current_period_end)}</dd>
                        </div>
                        <div>
                            <dt className="text-gray-400">{t("account.paymentMethod")}</dt>
                            <dd className="font-medium mt-0.5">{sub.payment_method_label ?? (sub.provider === "manual" ? t("account.grantedByAdmin") : "—")}</dd>
                        </div>
                        {sub.pending_plan_code && (
                            <div className="col-span-2">
                                <dt className="text-gray-400">{t("account.nextPlan")}</dt>
                                <dd className="font-medium mt-0.5">{sub.pending_plan_code} ({sub.pending_period})</dd>
                            </div>
                        )}
                    </dl>
                )}

                <div className="mt-6 flex flex-wrap gap-3">
                    <Link to="/pricing"><Button>{paid ? t("account.changePlan") : t("account.upgrade")}</Button></Link>
                    {paid && !sub.cancel_at_period_end && (
                        <Button variant="secondary" loading={busy} onClick={() => run(() => api.cancelSubscription(), t("account.cancelDone"))}>{t("account.cancelSubscription")}</Button>
                    )}
                    {paid && sub.cancel_at_period_end && (
                        <Button variant="secondary" loading={busy} onClick={() => run(() => api.checkout(plan.code, sub.period!), t("account.resumeDone"))}>{t("account.resume")}</Button>
                    )}
                </div>
                {message && <div className="mt-4"><Alert type={message.type}>{message.text}</Alert></div>}
            </Card>

            {isMock && paid && sub.provider === "mock" && (
                <Card className="p-6 border-dashed border-amber-300 bg-amber-50/40">
                    <div className="flex items-center gap-2 mb-2">
                        <h3 className="font-semibold">{t("account.demoTools")}</h3>
                        <Badge color="amber">{t("checkout.demoBadge")}</Badge>
                    </div>
                    <p className="text-sm text-gray-600 mb-4">{t("account.demoToolsText")}</p>
                    <div className="flex flex-wrap gap-3">
                        <Button variant="secondary" size="sm" loading={busy} onClick={() => run(async () => { const r = await api.demoRenewNow(); return r; }, t("account.demoRenewDone"))}>{t("account.demoRenew")}</Button>
                        <Button variant="secondary" size="sm" loading={busy} onClick={() => run(() => api.demoFailNext(), t("account.demoFailDone"))}>{t("account.demoFail")}</Button>
                    </div>
                </Card>
            )}
        </div>
    );
}

function PaymentsTab() {
    const { t } = useTranslation();
    const [payments, setPayments] = useState<Payment[] | null>(null);
    useEffect(() => { api.getPayments().then(({ data }) => setPayments(data ?? [])); }, []);
    if (!payments) return <Spinner />;
    if (payments.length === 0) return <p className="text-sm text-gray-500">{t("account.noPayments")}</p>;
    return (
        <Card className="overflow-x-auto">
            <table className="w-full text-sm">
                <thead>
                    <tr className="text-left text-gray-500 border-b border-gray-100">
                        <th className="px-4 py-3 font-medium">{t("account.payments.date")}</th>
                        <th className="px-4 py-3 font-medium">{t("account.payments.description")}</th>
                        <th className="px-4 py-3 font-medium">{t("account.payments.amount")}</th>
                        <th className="px-4 py-3 font-medium">{t("account.payments.status")}</th>
                    </tr>
                </thead>
                <tbody>
                    {payments.map((p) => (
                        <tr key={p.id} className="border-b border-gray-50 last:border-0">
                            <td className="px-4 py-3 whitespace-nowrap text-gray-600">{formatDateTime(p.paid_at ?? p.created_at)}</td>
                            <td className="px-4 py-3">
                                {t(`account.payments.kind.${p.kind}`)} · {p.plan_code} · {t(p.period === "month" ? "checkout.month" : "checkout.year")}
                                {p.card && <span className="text-gray-400"> · {p.card.brand} •••• {p.card.last4}</span>}
                                {p.failure_reason && <div className="text-xs text-red-500">{p.failure_reason}</div>}
                            </td>
                            <td className="px-4 py-3 tabular-nums font-medium">{formatRub(p.amount)}</td>
                            <td className="px-4 py-3"><Badge color={PAYMENT_BADGE[p.status]}>{t(`account.payments.statuses.${p.status}`)}</Badge></td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </Card>
    );
}

function UsageTab() {
    const { t } = useTranslation();
    const me = useAuth((s) => s.me);
    if (!me) return null;
    const { plan, usage, workflows } = me;
    const l = plan.limits;
    return (
        <Card className="p-6 max-w-2xl space-y-5">
            <h2 className="font-semibold">{t("account.usageMonth")}</h2>
            <UsageBar label={t("pricing.rows.aiRuns")} used={usage.ai_run} limit={l.ai_run} />
            <UsageBar label={t("pricing.rows.regularRuns")} used={usage.regular_run} limit={l.regular_run} />
            <UsageBar label={t("pricing.rows.aiChat")} used={usage.ai_chat} limit={l.ai_chat} />
            <h2 className="font-semibold pt-2">{t("account.usageNow")}</h2>
            <UsageBar label={t("pricing.rows.aiWorkflows")} used={workflows.ai_workflows} limit={l.ai_workflows} />
            <UsageBar label={t("pricing.rows.regularWorkflows")} used={workflows.regular_workflows} limit={l.regular_workflows} />
            <UsageBar label={t("pricing.rows.telegram")} used={workflows.telegram_triggers} limit={l.telegram_triggers} />
            <p className="text-xs text-gray-400">{t("account.usageNote", { days: l.history_days ?? "∞" })}</p>
        </Card>
    );
}
