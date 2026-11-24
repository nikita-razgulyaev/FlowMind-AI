import { CheckCircle2 } from "lucide-react";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import { useAuth } from "../../store/auth";
import type { FeedbackType } from "../../types/app";
import { Alert, Button, Field, Select } from "../common/ui";

export const MESSAGE_MIN = 3;
export const MESSAGE_MAX = 3000;
const TYPES: FeedbackType[] = ["question", "bug", "idea", "payment", "other"];
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function newClientId(): string {
    const c = globalThis.crypto as Crypto | undefined;
    if (c?.randomUUID) return c.randomUUID();
    return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
}

interface Props {
    /** Черновик хранит родитель, чтобы закрытое случайно окно не стоило человеку набранного текста. */
    draft?: string;
    onDraftChange?: (value: string) => void;
    autoFocus?: boolean;
}

/**
 * Форма обратной связи. Защита от ботов устроена так, чтобы не мешать людям:
 *  — скрытое поле-ловушка (`fm_extra`): человек его не видит и не фокусирует, бот заполняет;
 *  — время от открытия формы до отправки: бот отправляет за миллисекунды.
 * Срабатывание не блокирует ничего у пользователя — обращение просто попадает в раздел «Спам», откуда его можно вернуть.
 */
export default function FeedbackForm({ draft = "", onDraftChange, autoFocus = false }: Props) {
    const { t } = useTranslation();
    const me = useAuth((s) => s.me);

    const [type, setType] = useState<FeedbackType>("question");
    const [message, setMessage] = useState(draft);
    const [name, setName] = useState(me?.user.name ?? "");
    const [email, setEmail] = useState(me?.user.email ?? "");
    const [hp, setHp] = useState("");
    const [sending, setSending] = useState(false);
    const [sent, setSent] = useState(false);
    const [error, setError] = useState("");

    // Если форма открыта с сохранённым черновиком, человек уже потратил на него время — «слишком быстро» к нему не относится.
    const openedAt = useRef(Date.now() - (draft ? 60_000 : 0));
    // Один ключ на всё открытие формы: повторная отправка после обрыва связи не создаст второе обращение.
    const clientId = useRef(newClientId());

    const changeMessage = (value: string) => {
        setMessage(value);
        onDraftChange?.(value);
    };

    const reset = () => {
        setType("question");
        changeMessage("");
        setHp("");
        setError("");
        setSent(false);
        openedAt.current = Date.now();
        clientId.current = newClientId();
    };

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        if (sending) return;
        const text = message.trim();
        if (text.length < MESSAGE_MIN) return setError(t("feedback.tooShort"));
        if (text.length > MESSAGE_MAX) return setError(t("feedback.tooLong", { max: MESSAGE_MAX }));
        if (email.trim() && !EMAIL_RE.test(email.trim())) return setError(t("feedback.badEmail"));

        setError("");
        setSending(true);
        const { error: apiError } = await api.sendFeedback({
            type,
            message: text,
            name: name.trim(),
            email: email.trim(),
            page: window.location.pathname,
            client_id: clientId.current,
            hp,
            elapsed_ms: Date.now() - openedAt.current,
        });
        setSending(false);
        if (apiError) {
            // Текст не очищаем: человек нажмёт «Отправить» ещё раз, а ключ повторной отправки защитит от дубля.
            setError(`${apiError} ${t("feedback.failedKeep")}`);
            return;
        }
        onDraftChange?.("");
        setSent(true);
    };

    if (sent) {
        return (
            <div className="py-6 text-center" role="status">
                <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-500" />
                <h3 className="mt-3 text-base font-semibold text-gray-800">{t("feedback.thanksTitle")}</h3>
                <p className="mt-1 text-sm text-gray-500">{t("feedback.thanksText")}</p>
                <Button variant="secondary" size="sm" className="mt-4" onClick={reset}>{t("feedback.sendAnother")}</Button>
            </div>
        );
    }

    const tooLong = message.trim().length > MESSAGE_MAX;
    return (
        <form onSubmit={submit} className="relative space-y-4" noValidate>
            {/* Ловушка для ботов. Не display:none — часть ботов такие поля пропускает. Для людей и скринридеров поле не существует. */}
            <div aria-hidden="true" style={{ position: "absolute", left: "-10000px", width: 1, height: 1, overflow: "hidden" }}>
                <input
                    type="text"
                    name="fm_extra"
                    tabIndex={-1}
                    autoComplete="off"
                    data-lpignore="true"
                    data-1p-ignore="true"
                    data-testid="feedback-trap"
                    value={hp}
                    onChange={(e) => setHp(e.target.value)}
                />
            </div>

            <Select label={t("feedback.type")} value={type} onChange={(e) => setType(e.target.value as FeedbackType)}>
                {TYPES.map((k) => <option key={k} value={k}>{t(`feedback.types.${k}`)}</option>)}
            </Select>

            <label className="block">
                <span className="mb-1 block text-sm font-medium text-gray-700">{t("feedback.message")}</span>
                <textarea
                    value={message}
                    onChange={(e) => changeMessage(e.target.value)}
                    placeholder={t("feedback.messagePlaceholder")}
                    rows={5}
                    autoFocus={autoFocus}
                    className="w-full resize-y rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:outline-hidden focus:ring-blue-500"
                />
                <span className={`mt-1 block text-right text-xs ${tooLong ? "text-red-600" : "text-gray-400"}`}>
                    {t("feedback.counter", { n: message.trim().length, max: MESSAGE_MAX })}
                </span>
            </label>

            <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("feedback.name")} value={name} maxLength={120} autoComplete="name" onChange={(e) => setName(e.target.value)} />
                <Field
                    label={t("feedback.email")}
                    type="email"
                    value={email}
                    maxLength={320}
                    autoComplete="email"
                    hint={me ? t("feedback.emailHintLoggedIn") : t("feedback.emailHint")}
                    onChange={(e) => setEmail(e.target.value)}
                />
            </div>

            {error && <Alert type="error">{error}</Alert>}

            <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="max-w-sm text-xs text-gray-400">{t("feedback.notice")}</p>
                <Button type="submit" loading={sending}>{t("feedback.send")}</Button>
            </div>
        </form>
    );
}
