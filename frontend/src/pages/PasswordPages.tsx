import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useAuth } from "../store/auth";
import AuthLayout from "../components/auth/AuthLayout";
import { Alert, Button, Field, Spinner } from "../components/common/ui";

export function ForgotPassword() {
    const { t } = useTranslation();
    const [email, setEmail] = useState("");
    const [sent, setSent] = useState(false);
    const [devLink, setDevLink] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        setLoading(true);
        const { data, error: err } = await api.forgotPassword(email);
        setLoading(false);
        if (err) return setError(err);
        setSent(true);
        setDevLink(data?.dev_link ?? null);
    };

    return (
        <AuthLayout title={t("auth.forgotTitle")} subtitle={t("auth.forgotSubtitle")}>
            {sent ? (
                <div className="space-y-3">
                    <Alert type="success">{t("auth.resetSent")}</Alert>
                    {devLink && (
                        <Alert type="info">
                            <p className="mb-1">{t("auth.demoLink")}</p>
                            <a href={devLink} className="underline break-all">{devLink}</a>
                        </Alert>
                    )}
                </div>
            ) : (
                <form onSubmit={submit} className="space-y-4">
                    <Field label={t("auth.email")} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
                    {error && <Alert type="error">{error}</Alert>}
                    <Button type="submit" loading={loading} className="w-full">{t("auth.sendLink")}</Button>
                </form>
            )}
            <Link to="/login" className="block mt-5 text-sm text-blue-600 hover:underline">{t("auth.backToLogin")}</Link>
        </AuthLayout>
    );
}

export function ResetPassword() {
    const { t } = useTranslation();
    const [params] = useSearchParams();
    const token = params.get("token") ?? "";
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [done, setDone] = useState(false);
    const [loading, setLoading] = useState(false);

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        setLoading(true);
        const { error: err } = await api.resetPassword(token, password);
        setLoading(false);
        if (err) return setError(err);
        setDone(true);
    };

    return (
        <AuthLayout title={t("auth.resetTitle")}>
            {done ? (
                <div className="space-y-4">
                    <Alert type="success">{t("auth.resetDone")}</Alert>
                    <Link to="/login" className="text-sm text-blue-600 hover:underline">{t("auth.login")}</Link>
                </div>
            ) : (
                <form onSubmit={submit} className="space-y-4">
                    <Field label={t("auth.newPassword")} type="password" required minLength={8} autoComplete="new-password" hint={t("auth.passwordHint")} value={password} onChange={(e) => setPassword(e.target.value)} />
                    {error && <Alert type="error">{error}</Alert>}
                    <Button type="submit" loading={loading} disabled={!token} className="w-full">{t("auth.setPassword")}</Button>
                </form>
            )}
        </AuthLayout>
    );
}

export function VerifyEmail() {
    const { t } = useTranslation();
    const [params] = useSearchParams();
    const navigate = useNavigate();
    const startSession = useAuth((s) => s.startSession);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const token = params.get("token");
        if (!token) return setError(t("errors.badLink"));
        api.verifyEmail(token).then(async ({ data, error: err }) => {
            if (data) {
                await startSession(data.access_token);
                navigate("/", { replace: true });
            } else setError(err ?? t("errors.badLink"));
        });
    }, []);

    return (
        <AuthLayout title={t("auth.verifyTitle")}>
            {error ? (
                <>
                    <Alert type="error">{error}</Alert>
                    <Link to="/login" className="block mt-4 text-sm text-blue-600 hover:underline">{t("auth.backToLogin")}</Link>
                </>
            ) : (
                <Spinner label={t("auth.verifying")} />
            )}
        </AuthLayout>
    );
}
