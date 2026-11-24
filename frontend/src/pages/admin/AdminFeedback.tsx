import { Download, Mail, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import ConfirmDialog from "../../components/ConfirmDialog";
import { Alert, Badge, Button, Card, Select, Spinner } from "../../components/common/ui";
import { formatDateTime } from "../../i18n";
import type { FeedbackItem, FeedbackStatus, FeedbackType } from "../../types/app";

const PAGE = 25;
const FILTERS: ("" | FeedbackStatus)[] = ["", "new", "in_progress", "done", "spam"];
const STATUS_COLORS: Record<FeedbackStatus, "blue" | "amber" | "green" | "red"> = { new: "blue", in_progress: "amber", done: "green", spam: "red" };
const TYPES: FeedbackType[] = ["question", "bug", "idea", "payment", "other"];

function FeedbackCard({ item, onChanged, onDelete, onNotice }: {
    item: FeedbackItem;
    onChanged: () => void;
    onDelete: (item: FeedbackItem) => void;
    onNotice: (n: { type: "success" | "error"; text: string }) => void;
}) {
    const { t } = useTranslation();
    const [note, setNote] = useState(item.admin_note);
    const [busy, setBusy] = useState(false);

    const patch = async (body: { status?: FeedbackStatus; admin_note?: string }, successText?: string) => {
        setBusy(true);
        const { error } = await api.adminFeedbackUpdate(item.id, body);
        setBusy(false);
        if (error) return onNotice({ type: "error", text: error });
        if (successText) onNotice({ type: "success", text: successText });
        onChanged();
    };

    const resend = async () => {
        setBusy(true);
        const { data, error } = await api.adminFeedbackForward(item.id);
        setBusy(false);
        if (error || data?.forward_status !== "sent") return onNotice({ type: "error", text: error || t("admin.feedback.forward.failed") });
        onNotice({ type: "success", text: t("admin.feedback.resent") });
        onChanged();
    };

    const who = item.email || item.name ? [item.name, item.email].filter(Boolean).join(" · ") : t("admin.feedback.guest");
    const reply = item.email ? `mailto:${item.email}?subject=${encodeURIComponent("Re: FlowMind AI")}` : "";

    return (
        <Card className="p-5 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
                <Badge color={STATUS_COLORS[item.status]}>{t(`admin.feedback.statusOne.${item.status}`)}</Badge>
                <Badge color="gray">{t(`feedback.types.${item.type}`)}</Badge>
                <span className="text-xs text-gray-400">{formatDateTime(item.created_at)}</span>
                <span className="ml-auto text-xs text-gray-400">#{item.id}</span>
            </div>

            <p className="whitespace-pre-wrap break-words text-sm text-gray-800">{item.message}</p>

            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                <span>{who}</span>
                {item.user_id && <span>{t("admin.feedback.account")} #{item.user_id}{item.plan ? ` · ${item.plan}` : ""}</span>}
                {item.page && <span>{t("admin.feedback.page")}: {item.page}</span>}
                {item.status === "spam" && item.spam_reason && <span className="text-red-600">{t(`admin.feedback.spamReason.${item.spam_reason}`, { defaultValue: item.spam_reason })}</span>}
                {item.status !== "spam" && <span>{t(`admin.feedback.forward.${item.forward_status}`)}</span>}
            </div>

            <div className="flex flex-wrap items-center gap-2">
                {item.status === "spam" ? (
                    <Button size="sm" disabled={busy} onClick={() => patch({ status: "new" })}>{t("admin.feedback.notSpam")}</Button>
                ) : (
                    <>
                        {(["new", "in_progress", "done"] as const).filter((s) => s !== item.status).map((s) => (
                            <Button key={s} size="sm" variant="secondary" disabled={busy} onClick={() => patch({ status: s })}>
                                {t(`admin.feedback.statusOne.${s}`)}
                            </Button>
                        ))}
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => patch({ status: "spam" })}>{t("admin.feedback.markSpam")}</Button>
                        {item.forward_status === "failed" && <Button size="sm" variant="ghost" disabled={busy} onClick={resend}>{t("admin.feedback.resend")}</Button>}
                    </>
                )}
                {reply && item.status !== "spam" && (
                    <a href={reply} className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-blue-600 hover:bg-blue-50">
                        <Mail className="h-3.5 w-3.5" /> {item.email}
                    </a>
                )}
                <button
                    type="button"
                    disabled={busy}
                    onClick={() => onDelete(item)}
                    className="ml-auto inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                >
                    <Trash2 className="h-3.5 w-3.5" /> {t("admin.feedback.delete")}
                </button>
            </div>

            <div className="flex gap-2">
                <input
                    value={note}
                    maxLength={2000}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder={t("admin.feedback.note")}
                    className="min-w-0 flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:border-blue-500 focus:ring-2 focus:outline-hidden focus:ring-blue-500"
                />
                <Button size="sm" variant="secondary" disabled={busy || note.trim() === item.admin_note} onClick={() => patch({ admin_note: note }, t("admin.feedback.noteSaved"))}>
                    {t("admin.feedback.saveNote")}
                </Button>
            </div>
        </Card>
    );
}

export default function AdminFeedback() {
    const { t } = useTranslation();
    const [status, setStatus] = useState<"" | FeedbackStatus>("");
    const [type, setType] = useState<"" | FeedbackType>("");
    const [search, setSearch] = useState("");
    const [q, setQ] = useState("");
    const [items, setItems] = useState<FeedbackItem[] | null>(null);
    const [total, setTotal] = useState(0);
    const [counts, setCounts] = useState<Record<FeedbackStatus, number>>({ new: 0, in_progress: 0, done: 0, spam: 0 });
    const [loadingMore, setLoadingMore] = useState(false);
    const [notice, setNotice] = useState<{ type: "success" | "error"; text: string } | null>(null);
    const [toDelete, setToDelete] = useState<FeedbackItem | null>(null);
    const [clearSpamOpen, setClearSpamOpen] = useState(false);
    const loaded = useRef(0);

    useEffect(() => {              // поиск срабатывает после паузы в наборе
        const id = setTimeout(() => setQ(search.trim()), 300);
        return () => clearTimeout(id);
    }, [search]);

    /** Перезагружает список с начала, но не меньше уже показанного количества — «Показать ещё» не сбрасывается после действия. */
    const reload = useCallback(async (keepLoaded: boolean) => {
        const limit = keepLoaded ? Math.min(100, Math.max(PAGE, loaded.current)) : PAGE;
        const { data, error } = await api.adminFeedback({ status, type, q, offset: 0, limit });
        if (error || !data) { setNotice({ type: "error", text: error || t("admin.feedback.error") }); setItems((prev) => prev ?? []); return; }
        setItems(data.items);
        setTotal(data.total);
        setCounts(data.counts);
        loaded.current = data.items.length;
    }, [status, type, q]);

    useEffect(() => { setItems(null); void reload(false); }, [reload]);

    const loadMore = async () => {
        setLoadingMore(true);
        const { data, error } = await api.adminFeedback({ status, type, q, offset: loaded.current, limit: PAGE });
        setLoadingMore(false);
        if (error || !data) return setNotice({ type: "error", text: error || t("admin.feedback.error") });
        setItems((prev) => [...(prev ?? []), ...data.items]);
        loaded.current += data.items.length;
        setTotal(data.total);
    };

    const exportCsv = async () => {
        const { blob, error } = await api.adminFeedbackCsv({ status, type, q });
        if (error || !blob) return setNotice({ type: "error", text: error || t("admin.feedback.error") });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `feedback-${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const confirmDelete = async () => {
        if (!toDelete) return;
        const { error } = await api.adminFeedbackDelete(toDelete.id);
        setToDelete(null);
        if (error) return setNotice({ type: "error", text: error });
        void reload(true);
    };

    const confirmClearSpam = async () => {
        setClearSpamOpen(false);
        const { data, error } = await api.adminFeedbackClearSpam();
        if (error || !data) return setNotice({ type: "error", text: error || t("admin.feedback.error") });
        setNotice({ type: "success", text: t("admin.feedback.cleared", { n: data.deleted }) });
        void reload(false);
    };

    const countFor = (f: "" | FeedbackStatus) => (f === "" ? counts.new + counts.in_progress + counts.done : counts[f]);

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
                {FILTERS.map((f) => (
                    <button
                        key={f || "all"}
                        onClick={() => setStatus(f)}
                        aria-pressed={status === f}
                        className={`rounded-full border px-3 py-1 text-sm transition-colors ${status === f ? "border-blue-600 bg-blue-50 text-blue-700" : "border-gray-200 text-gray-600 hover:bg-gray-50"}`}
                    >
                        {f === "" ? t("admin.feedback.all") : t(`admin.feedback.status.${f}`)} <span className="tabular-nums text-gray-400">{countFor(f)}</span>
                    </button>
                ))}
            </div>

            <div className="flex flex-wrap items-end gap-3">
                <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t("admin.feedback.search")}
                    aria-label={t("admin.feedback.search")}
                    className="min-w-[16rem] flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:outline-hidden focus:ring-blue-500"
                />
                <div className="w-48">
                    <Select value={type} onChange={(e) => setType(e.target.value as "" | FeedbackType)} aria-label={t("feedback.type")}>
                        <option value="">{t("admin.feedback.allTypes")}</option>
                        {TYPES.map((k) => <option key={k} value={k}>{t(`feedback.types.${k}`)}</option>)}
                    </Select>
                </div>
                <Button variant="secondary" onClick={exportCsv}><Download className="h-4 w-4" /> {t("admin.feedback.exportCsv")}</Button>
                {status === "spam" && counts.spam > 0 && <Button variant="danger" onClick={() => setClearSpamOpen(true)}>{t("admin.feedback.clearSpam")}</Button>}
            </div>

            <p className="text-xs text-gray-400">{t("admin.feedback.backupHint")}</p>
            {notice && <div onClick={() => setNotice(null)}><Alert type={notice.type}>{notice.text}</Alert></div>}

            {!items ? <Spinner /> : items.length === 0 ? (
                <Card className="p-10 text-center text-sm text-gray-400">{status === "spam" ? t("admin.feedback.emptySpam") : t("admin.feedback.empty")}</Card>
            ) : (
                <>
                    <p className="text-sm text-gray-500">{t("admin.feedback.total", { n: total })}</p>
                    <div className="space-y-3">
                        {items.map((item) => (
                            <FeedbackCard key={item.id} item={item} onChanged={() => void reload(true)} onDelete={setToDelete} onNotice={setNotice} />
                        ))}
                    </div>
                    {items.length < total && (
                        <div className="text-center">
                            <Button variant="secondary" loading={loadingMore} onClick={loadMore}>{t("admin.feedback.loadMore")}</Button>
                        </div>
                    )}
                </>
            )}

            <ConfirmDialog
                open={!!toDelete}
                title={t("admin.feedback.deleteConfirmTitle")}
                message={t("admin.feedback.deleteConfirmText")}
                confirmLabel={t("admin.feedback.delete")}
                onCancel={() => setToDelete(null)}
                onConfirm={confirmDelete}
            />
            <ConfirmDialog
                open={clearSpamOpen}
                title={t("admin.feedback.clearSpamTitle")}
                message={t("admin.feedback.clearSpamText")}
                confirmLabel={t("admin.feedback.clearSpam")}
                onCancel={() => setClearSpamOpen(false)}
                onConfirm={confirmClearSpam}
            />
        </div>
    );
}
