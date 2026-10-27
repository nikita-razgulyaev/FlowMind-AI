import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useAuth } from "../store/auth";
import AuthLayout from "../components/auth/AuthLayout";
import { Alert, Button, Field } from "../components/common/ui";

export default function Register() {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const startSession = useAuth((s) => s.startSession);
    const [params] = useSearchParams();
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [verifyLink, setVerifyLink] = useState<string | null | undefined>(undefined);

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        if (password.length < 8) {
            setError(t("auth.passwordTooShort"));
            return;
        }
        setLoading(true);
        setError(null);
        const { data, error: err } = await api.register(email, password, name);
        if (!data) {
            setError(err ?? t("errors.unknown"));
            setLoading(false);
            return;
        }
        if (data.verification_required) {
            setVerifyLink(data.dev_link ?? null);
            setLoading(false);
            return;
        }
        await startSession(data.access_token!);
        // пришли с выбранным платным тарифом на лендинге — сразу ведём на оплату
        const plan = params.get("plan");
        const period = params.get("period") === "month" ? "month" : "year";
        navigate(plan && plan !== "free" ? `/checkout?plan=${plan}&period=${period}` : "/", { replace: true });
    };

    if (verifyLink !== undefined) {
        return (
            <AuthLayout title={t("auth.checkEmailTitle")} subtitle={t("auth.checkEmailText", { email })}>
                {verifyLink && (
                    <Alert type="info">
                        <p className="mb-1">{t("auth.demoLink")}</p>
                        <a href={verifyLink} className="underline break-all">{verifyLink}</a>
                    </Alert>
                )}
                <Link to="/login" className="block mt-5 text-sm text-blue-600 hover:underline">{t("auth.backToLogin")}</Link>
            </AuthLayout>
        );
    }

    return (
        <AuthLayout title={t("auth.registerTitle")} subtitle={t("auth.registerSubtitle")}>
            <form onSubmit={submit} className="space-y-4">
                <Field label={t("auth.name")} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
                <Field label={t("auth.email")} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                <Field label={t("auth.password")} type="password" required autoComplete="new-password" hint={t("auth.passwordHint")} value={password} onChange={(e) => setPassword(e.target.value)} />
                {error && <Alert type="error">{error}</Alert>}
                <Button type="submit" loading={loading} className="w-full">{t("auth.register")}</Button>
            </form>
            <p className="mt-5 text-sm text-gray-500">
                {t("auth.haveAccount")}{" "}
                <Link to="/login" className="text-blue-600 hover:underline">{t("auth.login")}</Link>
            </p>
        </AuthLayout>
    );
}
