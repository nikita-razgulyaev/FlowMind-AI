import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2, XCircle } from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../store/auth";
import AppLayout from "../components/AppLayout";
import { Card, Spinner } from "../components/common/ui";

/** Страница, на которую ЮKassa возвращает пользователя после оплаты. Статус подтверждает вебхук — ждём его. */
export default function BillingReturn() {
    const { t } = useTranslation();
    const [params] = useSearchParams();
    const loadMe = useAuth((s) => s.loadMe);
    const [status, setStatus] = useState<"waiting" | "succeeded" | "failed" | "timeout">("waiting");
    const [reason, setReason] = useState<string | null>(null);

    useEffect(() => {
        const id = Number(params.get("payment"));
        let attempts = 0;
        let stopped = false;
        const poll = async () => {
            if (stopped) return;
            const { data } = await api.getPayment(id);
            if (data?.status === "succeeded") {
                await loadMe();
                return setStatus("succeeded");
            }
            if (data?.status === "failed" || data?.status === "canceled") {
                setReason(data.failure_reason);
                return setStatus("failed");
            }
            if (++attempts > 30) return setStatus("timeout");
            setTimeout(poll, 2000);
        };
        void poll();
        return () => { stopped = true; };
    }, []);

    return (
        <AppLayout>
            <Card className="max-w-lg mx-auto p-8 text-center">
                {status === "waiting" && <Spinner label={t("billingReturn.waiting")} />}
                {status === "succeeded" && (
                    <>
                        <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto" />
                        <h1 className="text-xl font-bold mt-4">{t("checkout.doneTitle")}</h1>
                        <p className="text-gray-600 mt-2">{t("checkout.doneSuccess")}</p>
                    </>
                )}
                {status === "failed" && (
                    <>
                        <XCircle className="w-14 h-14 text-red-500 mx-auto" />
                        <h1 className="text-xl font-bold mt-4">{t("checkout.failedTitle")}</h1>
                        <p className="text-gray-600 mt-2">{reason ?? t("checkout.declined")}</p>
                    </>
                )}
                {status === "timeout" && <p className="text-gray-600">{t("billingReturn.timeout")}</p>}
                {status !== "waiting" && (
                    <div className="mt-6 flex justify-center gap-4 text-sm">
                        <Link to="/account?tab=subscription" className="text-blue-600 hover:underline">{t("checkout.toAccount")}</Link>
                        <Link to="/pricing" className="text-gray-500 hover:underline">{t("checkout.backToPricing")}</Link>
                    </div>
                )}
            </Card>
        </AppLayout>
    );
}
