import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2, CreditCard, Lock, ShieldCheck, XCircle } from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../store/auth";
import type { CardInput, Payment, Period, Quote } from "../types/app";
import AppLayout from "../components/AppLayout";
import { Alert, Badge, Button, Card, Field, Spinner } from "../components/common/ui";
import { formatDate, formatRub } from "../i18n";

const formatCardNumber = (v: string) => v.replace(/\D/g, "").slice(0, 19).replace(/(.{4})/g, "$1 ").trim();
const formatExpiry = (v: string) => {
    const d = v.replace(/\D/g, "").slice(0, 4);
    return d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d;
};

type Stage = "form" | "processing" | "3ds" | "success" | "failed" | "done";

export default function Checkout() {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const planCode = params.get("plan") ?? "";
    const period = (params.get("period") === "month" ? "month" : "year") as Period;
    const { config, me, loadMe } = useAuth();
    const isMock = config?.payment_provider === "mock";

    const [quote, setQuote] = useState<Quote | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [stage, setStage] = useState<Stage>("form");
    const [error, setError] = useState<string | null>(null);
    const [payment, setPayment] = useState<Payment | null>(null);
    const [doneMessage, setDoneMessage] = useState("");
    const [testCards, setTestCards] = useState<{ number: string; result: string }[]>([]);
    const [card, setCard] = useState({ number: "", expiry: "", cvc: "", holder: "" });

    useEffect(() => {
        api.quote(planCode, period).then(({ data, error: err }) => (data ? setQuote(data) : setLoadError(err ?? t("errors.unknown"))));
        if (isMock) api.getTestCards().then(({ data }) => data && setTestCards(data));
    }, [planCode, period, isMock]);

    const finish = async (message: string) => {
        await loadMe();
        setDoneMessage(message);
        setStage("done");
    };

    // Смена тарифа без немедленной оплаты: отмена, возобновление, понижение
    const applyWithoutPayment = async () => {
        setStage("processing");
        const { data, error: err } = await api.checkout(planCode, period);
        if (!data) {
            setError(err ?? t("errors.unknown"));
            return setStage("form");
        }
        const messages: Record<string, string> = {
            cancel: t("checkout.doneCancel", { date: formatDate(data.effective_at) }),
            scheduled: t("checkout.doneScheduled", { date: formatDate(data.effective_at) }),
            resumed: t("checkout.doneResumed"),
        };
        await finish(messages[data.action] ?? t("checkout.doneGeneric"));
    };

    const pay = async (e?: FormEvent) => {
        e?.preventDefault();
        setError(null);
        setStage("processing");
        const { data, error: err } = await api.checkout(planCode, period);
        if (!data?.payment) {
            setError(err ?? t("errors.unknown"));
            return setStage("form");
        }
        const created = data.payment;
        setPayment(created);

        if (!isMock) {
            if (created.confirmation_url) window.location.href = created.confirmation_url;
            else {
                setError(t("checkout.noConfirmationUrl"));
                setStage("form");
            }
            return;
        }

        const [mm, yy] = card.expiry.split("/");
        const input: CardInput = {
            number: card.number, exp_month: Number(mm), exp_year: Number(yy), cvc: card.cvc, holder: card.holder,
        };
        const { data: paid, error: payErr } = await api.mockPay(created.id, input);
        if (!paid) {
            setError(payErr ?? t("errors.unknown"));
            return setStage("form");
        }
        setPayment(paid);
        if (paid.status === "requires_action") return setStage("3ds");
        if (paid.status === "succeeded") return finish(t("checkout.doneSuccess"));
        if (paid.status === "pending") {
            // mock: оплата принята, статус станет succeeded через ~10 с — ждём, не создаём новый платёж
            return waitForPayment(paid.id);
        }
        setError(paid.failure_reason ?? t("checkout.declined"));
        setStage("failed");
    };

    const waitForPayment = async (paymentId: number) => {
        setStage("processing");
        const deadline = Date.now() + 20000;
        while (Date.now() < deadline) {
            await new Promise((r) => setTimeout(r, 1500));
            const { data } = await api.getPayment(paymentId);
            if (!data) continue;
            setPayment(data);
            if (data.status === "succeeded") return finish(t("checkout.doneSuccess"));
            if (data.status === "failed" || data.status === "canceled") {
                setError(data.failure_reason ?? t("checkout.declined"));
                return setStage("failed");
            }
        }
        setError(t("checkout.paymentTimeout") ?? "Платёж ещё обрабатывается. Обновите страницу через минуту.");
        setStage("failed");
    };

    const confirm3ds = async (approve: boolean) => {
        if (!payment) return;
        setStage("processing");
        const { data, error: err } = await api.mockConfirm3ds(payment.id, approve);
        if (!data) {
            setError(err ?? t("errors.unknown"));
            return setStage("failed");
        }
        setPayment(data);
        if (data.status === "succeeded") return finish(t("checkout.doneSuccess"));
        if (data.status === "pending") return waitForPayment(data.id);
        setError(data.failure_reason ?? err ?? t("checkout.declined"));
        setStage("failed");
    };

    if (!me) return <Spinner />;
    if (loadError) {
        return (
            <AppLayout>
                <Alert type="error">{loadError}</Alert>
                <Link to="/pricing" className="inline-block mt-4 text-blue-600 hover:underline">{t("checkout.backToPricing")}</Link>
            </AppLayout>
        );
    }
    if (!quote) return <AppLayout><Spinner /></AppLayout>;

    if (stage === "done") {
        return (
            <AppLayout>
                <Card className="max-w-lg mx-auto p-8 text-center">
                    <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto" />
                    <h1 className="text-xl font-bold mt-4">{t("checkout.doneTitle")}</h1>
                    <p className="text-gray-600 mt-2">{doneMessage}</p>
                    <div className="mt-6 flex gap-3 justify-center">
                        <Button onClick={() => navigate("/account?tab=subscription")}>{t("checkout.toAccount")}</Button>
                        <Button variant="secondary" onClick={() => navigate("/")}>{t("checkout.toApp")}</Button>
                    </div>
                </Card>
            </AppLayout>
        );
    }

    const needsPayment = quote.action === "pay";
    const actionText: Record<string, string> = {
        schedule: t("checkout.scheduleInfo", { date: formatDate(quote.effective_at) }),
        cancel: t("checkout.cancelInfo", { date: formatDate(quote.effective_at) }),
        resume: t("checkout.resumeInfo"),
    };

    return (
        <AppLayout>
            <h1 className="text-2xl font-bold text-gray-900 mb-6">{t("checkout.title")}</h1>
            <div className="grid md:grid-cols-5 gap-6">
                <Card className="md:col-span-2 p-6 h-fit">
                    <h2 className="font-semibold text-gray-900">{t("checkout.summary")}</h2>
                    <div className="mt-4 flex items-center justify-between">
                        <span className="text-gray-600">{t("checkout.plan")}</span>
                        <span className="font-medium">{quote.plan.name}</span>
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                        <span className="text-gray-600">{t("checkout.period")}</span>
                        <span className="font-medium">{t(period === "month" ? "checkout.month" : "checkout.year")}</span>
                    </div>
                    {needsPayment && (
                        <>
                            <div className="mt-2 flex justify-between text-sm">
                                <span className="text-gray-600">{t("checkout.price")}</span>
                                <span>{formatRub(quote.price)}</span>
                            </div>
                            {quote.credit > 0 && (
                                <div className="mt-1 flex justify-between text-sm text-emerald-700">
                                    <span>{t("checkout.credit")}</span>
                                    <span>−{formatRub(quote.credit)}</span>
                                </div>
                            )}
                            <div className="mt-4 pt-4 border-t border-gray-100 flex justify-between items-baseline">
                                <span className="font-semibold">{t("checkout.total")}</span>
                                <span className="text-2xl font-extrabold tabular-nums">{formatRub(quote.amount)}</span>
                            </div>
                            <p className="text-xs text-gray-400 mt-3">
                                {t(period === "month" ? "checkout.renewsMonthly" : "checkout.renewsYearly", { price: formatRub(quote.price) })}
                            </p>
                        </>
                    )}
                </Card>

                <Card className="md:col-span-3 p-6">
                    {!needsPayment ? (
                        <div className="space-y-4">
                            <Alert type="info">{actionText[quote.action]}</Alert>
                            {error && <Alert type="error">{error}</Alert>}
                            <Button onClick={applyWithoutPayment} loading={stage === "processing"}>{t("checkout.confirm")}</Button>
                        </div>
                    ) : stage === "3ds" ? (
                        <div className="text-center py-4 space-y-4">
                            <ShieldCheck className="w-12 h-12 text-blue-600 mx-auto" />
                            <h2 className="font-semibold text-lg">{t("checkout.threeDsTitle")}</h2>
                            <p className="text-sm text-gray-500">{t("checkout.threeDsText")}</p>
                            <div className="flex justify-center gap-3">
                                <Button variant="success" onClick={() => confirm3ds(true)}>{t("checkout.threeDsApprove")}</Button>
                                <Button variant="secondary" onClick={() => confirm3ds(false)}>{t("checkout.threeDsDecline")}</Button>
                            </div>
                        </div>
                    ) : stage === "failed" ? (
                        <div className="text-center py-4 space-y-4">
                            <XCircle className="w-12 h-12 text-red-500 mx-auto" />
                            <h2 className="font-semibold text-lg">{t("checkout.failedTitle")}</h2>
                            <p className="text-sm text-gray-600">{error}</p>
                            <Button onClick={() => { setError(null); setStage("form"); }}>{t("checkout.tryAgain")}</Button>
                        </div>
                    ) : isMock ? (
                        <form onSubmit={pay} className="space-y-4">
                            <div className="flex items-center gap-2">
                                <CreditCard className="w-5 h-5 text-gray-500" />
                                <h2 className="font-semibold text-gray-900">{t("checkout.cardTitle")}</h2>
                                <Badge color="amber">{t("checkout.demoBadge")}</Badge>
                            </div>
                            <Alert type="warning">{t("checkout.demoNotice")}</Alert>
                            <Field label={t("checkout.cardNumber")} inputMode="numeric" autoComplete="off" placeholder="4242 4242 4242 4242" required
                                value={card.number} onChange={(e) => setCard({ ...card, number: formatCardNumber(e.target.value) })} />
                            <div className="grid grid-cols-2 gap-4">
                                <Field label={t("checkout.expiry")} inputMode="numeric" autoComplete="off" placeholder="12/30" required pattern="\d{2}/\d{2}"
                                    value={card.expiry} onChange={(e) => setCard({ ...card, expiry: formatExpiry(e.target.value) })} />
                                <Field label="CVC" inputMode="numeric" autoComplete="off" placeholder="123" required maxLength={4} type="password"
                                    value={card.cvc} onChange={(e) => setCard({ ...card, cvc: e.target.value.replace(/\D/g, "") })} />
                            </div>
                            <Field label={t("checkout.holder")} autoComplete="off" placeholder="IVAN IVANOV" value={card.holder}
                                onChange={(e) => setCard({ ...card, holder: e.target.value.toUpperCase() })} />
                            {error && <Alert type="error">{error}</Alert>}
                            <Button type="submit" size="lg" loading={stage === "processing"} className="w-full">
                                <Lock className="w-4 h-4" /> {t("checkout.pay", { amount: formatRub(quote.amount) })}
                            </Button>
                            {testCards.length > 0 && (
                                <div className="pt-2 border-t border-gray-100">
                                    <p className="text-xs font-medium text-gray-500 mb-2">{t("checkout.testCards")}</p>
                                    <div className="space-y-1">
                                        {testCards.map((c) => (
                                            <button type="button" key={c.number}
                                                onClick={() => setCard({ number: c.number, expiry: "12/35", cvc: "123", holder: "TEST USER" })}
                                                className="w-full flex justify-between text-xs px-2 py-1.5 rounded-md hover:bg-gray-50 text-left">
                                                <span className="font-mono text-gray-700">{c.number}</span>
                                                <span className="text-gray-400">{c.result}</span>
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </form>
                    ) : (
                        <div className="space-y-4">
                            <h2 className="font-semibold text-gray-900">{t("checkout.redirectTitle")}</h2>
                            <p className="text-sm text-gray-500">{t("checkout.redirectText")}</p>
                            {error && <Alert type="error">{error}</Alert>}
                            <Button size="lg" onClick={() => pay()} loading={stage === "processing"} className="w-full">
                                <Lock className="w-4 h-4" /> {t("checkout.goToPayment", { amount: formatRub(quote.amount) })}
                            </Button>
                        </div>
                    )}
                </Card>
            </div>
        </AppLayout>
    );
}
