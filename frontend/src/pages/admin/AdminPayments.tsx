import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { Payment } from "../../types/app";
import { Badge, Card, Select, Spinner } from "../../components/common/ui";
import { formatDateTime, formatRub } from "../../i18n";

const COLORS: Record<string, "green" | "amber" | "red" | "gray"> = { succeeded: "green", pending: "amber", requires_action: "amber", failed: "red", canceled: "gray" };

export default function AdminPayments() {
    const { t } = useTranslation();
    const [status, setStatus] = useState("");
    const [rows, setRows] = useState<Payment[] | null>(null);
    useEffect(() => { setRows(null); api.adminPayments(status).then(({ data }) => setRows(data ?? [])); }, [status]);

    return (
        <div className="space-y-4">
            <div className="max-w-xs">
                <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                    <option value="">{t("admin.payments.all")}</option>
                    {["succeeded", "pending", "requires_action", "failed"].map((s) => <option key={s} value={s}>{t(`account.payments.statuses.${s}`)}</option>)}
                </Select>
            </div>
            {!rows ? <Spinner /> : (
                <Card className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-gray-500 border-b border-gray-100">
                                {["date", "user", "plan", "amount", "provider", "status"].map((c) => <th key={c} className="px-4 py-3 font-medium">{t(`admin.payments.cols.${c}`)}</th>)}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((p) => (
                                <tr key={p.id} className="border-b border-gray-50 last:border-0">
                                    <td className="px-4 py-3 whitespace-nowrap text-gray-600">{formatDateTime(p.created_at)}</td>
                                    <td className="px-4 py-3">{p.user_email ?? "—"}</td>
                                    <td className="px-4 py-3">{p.plan_code} · {p.period}</td>
                                    <td className="px-4 py-3 tabular-nums font-medium">{formatRub(p.amount)}</td>
                                    <td className="px-4 py-3 text-gray-500">{p.provider}</td>
                                    <td className="px-4 py-3"><Badge color={COLORS[p.status]}>{t(`account.payments.statuses.${p.status}`)}</Badge></td>
                                </tr>
                            ))}
                            {rows.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">—</td></tr>}
                        </tbody>
                    </table>
                </Card>
            )}
        </div>
    );
}
