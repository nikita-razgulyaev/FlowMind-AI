import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import { Alert, Button, Card, Field, Spinner } from "../../components/common/ui";
import { formatDateTime } from "../../i18n";

export default function AdminSystem() {
    const { t } = useTranslation();
    const [settings, setSettings] = useState<{ ai_enabled: boolean; ai_daily_cap: number } | null>(null);
    const [cap, setCap] = useState("");
    const [audit, setAudit] = useState<any[]>([]);
    const [msg, setMsg] = useState<string | null>(null);

    const load = async () => {
        const { data } = await api.adminSettings();
        if (data) { setSettings(data); setCap(String(data.ai_daily_cap)); }
        const { data: log } = await api.adminAudit();
        setAudit(log ?? []);
    };
    useEffect(() => { void load(); }, []);
    if (!settings) return <Spinner />;

    const save = async (body: Record<string, any>) => {
        const { error } = await api.adminSaveSettings(body);
        setMsg(error ?? t("admin.system.saved"));
        await load();
    };

    return (
        <div className="space-y-6 max-w-3xl">
            <Card className="p-5 space-y-4">
                <h2 className="font-semibold">{t("admin.system.aiTitle")}</h2>
                <p className="text-sm text-gray-500">{t("admin.system.aiText")}</p>
                <div className="flex items-center gap-3">
                    <Button variant={settings.ai_enabled ? "danger" : "success"} onClick={() => save({ ai_enabled: !settings.ai_enabled })}>
                        {settings.ai_enabled ? t("admin.system.disableAi") : t("admin.system.enableAi")}
                    </Button>
                    <span className="text-sm text-gray-500">{settings.ai_enabled ? t("admin.stats.aiOn") : t("admin.stats.aiOff")}</span>
                </div>
                <div className="flex items-end gap-3 max-w-xs">
                    <Field label={t("admin.system.dailyCap")} type="number" min={0} value={cap} onChange={(e) => setCap(e.target.value)} />
                    <Button variant="secondary" onClick={() => save({ ai_daily_cap: Number(cap) })}>{t("account.save")}</Button>
                </div>
                {msg && <Alert type="info">{msg}</Alert>}
            </Card>

            <Card className="p-5">
                <h2 className="font-semibold mb-3">{t("admin.system.audit")}</h2>
                {audit.length === 0 ? <p className="text-sm text-gray-400">—</p> : (
                    <ul className="divide-y divide-gray-50 text-sm">
                        {audit.map((a) => (
                            <li key={a.id} className="py-2 flex justify-between gap-4">
                                <span><b>{a.action}</b> <span className="text-gray-500">{a.target}</span><br /><span className="text-xs text-gray-400">{a.admin_email}</span></span>
                                <span className="text-xs text-gray-400 whitespace-nowrap">{formatDateTime(a.created_at)}</span>
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
        </div>
    );
}
