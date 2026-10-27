import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useAuth } from "../store/auth";
import AuthLayout from "../components/auth/AuthLayout";
import { Alert, Button, Field } from "../components/common/ui";

export default function Login() {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const location = useLocation();
    const startSession = useAuth((s) => s.startSession);
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [needsVerification, setNeedsVerification] = useState(false);
    const [notice, setNotice] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const from = (location.state as { from?: string } | null)?.from ?? "/";

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        const { data, error: err, code } = await api.login(email, password);
        if (data) {
            await startSession(data.access_token);
            navigate(from, { replace: true });
            return;
        }
        setNeedsVerification(code === "email_not_verified");
        setError(err ?? t("errors.unknown"));
        setLoading(false);
    };

    const resend = async () => {
        const { data } = await api.resendVerification(email);
        setNotice(data?.dev_link ? `${t("auth.verificationSent")} ${data.dev_link}` : t("auth.verificationSent"));
    };

    return (
        <AuthLayout title={t("auth.loginTitle")} subtitle={t("auth.loginSubtitle")}>
            <form onSubmit={submit} className="space-y-4">
                <Field label={t("auth.email")} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                <Field label={t("auth.password")} type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                {error && <Alert type="error">{error}</Alert>}
                {needsVerification && (
                    <button type="button" onClick={resend} className="text-sm text-blue-600 hover:underline">
                        {t("auth.resendVerification")}
                    </button>
                )}
                {notice && <Alert type="info"><span className="break-all">{notice}</span></Alert>}
                <Button type="submit" loading={loading} className="w-full">{t("auth.login")}</Button>
            </form>
            <div className="mt-5 flex justify-between text-sm">
                <Link to="/forgot-password" className="text-gray-500 hover:text-gray-700">{t("auth.forgot")}</Link>
                <Link to="/register" className="text-blue-600 hover:underline">{t("auth.noAccount")}</Link>
            </div>
        </AuthLayout>
    );
}
