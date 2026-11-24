import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../store/auth";
import ContactsList, { hasContacts } from "./ContactsList";
import FeedbackForm from "./FeedbackForm";

interface Props {
    open: boolean;
    onClose: () => void;
}

/** Окно обратной связи из приложения. Остаётся смонтированным у родителя, поэтому черновик переживает закрытие. */
export default function FeedbackModal({ open, onClose }: Props) {
    const { t } = useTranslation();
    const contacts = useAuth((s) => s.config?.contacts);
    const [draft, setDraft] = useState("");

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [open, onClose]);

    if (!open) return null;
    return (
        // Клик по фону окно не закрывает: слишком легко потерять набранный текст. Закрыть можно крестиком или Esc.
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4">
            <div role="dialog" aria-modal="true" aria-label={t("feedback.title")} className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-2xl">
                <div className="mb-4 flex items-start justify-between gap-4">
                    <div>
                        <h2 className="text-lg font-semibold text-gray-800">{t("feedback.title")}</h2>
                        <p className="mt-1 text-sm text-gray-500">{t("feedback.subtitle")}</p>
                    </div>
                    <button onClick={onClose} aria-label={t("feedback.close")} className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
                        <X className="h-5 w-5" />
                    </button>
                </div>
                <FeedbackForm draft={draft} onDraftChange={setDraft} autoFocus />
                {hasContacts(contacts) && (
                    <div className="mt-5 border-t border-gray-100 pt-4">
                        <p className="mb-2 text-xs text-gray-400">{t("contacts.alsoWrite")}</p>
                        <ContactsList contacts={contacts} variant="compact" />
                    </div>
                )}
            </div>
        </div>
    );
}
