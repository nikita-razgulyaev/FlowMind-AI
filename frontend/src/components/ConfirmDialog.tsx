import { useEffect } from "react";

interface Props {
    open: boolean;
    title: string;
    message: string;
    confirmLabel: string;
    cancelLabel?: string;
    onConfirm: () => void;
    onCancel: () => void;
}

/** Окно подтверждения опасного или необратимого действия. Esc и клик по фону отменяют, Enter подтверждает. */
export default function ConfirmDialog({ open, title, message, confirmLabel, cancelLabel = "Отмена", onConfirm, onCancel }: Props) {
    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") onCancel();
            if (e.key === "Enter") onConfirm();
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [open, onConfirm, onCancel]);

    if (!open) return null;
    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4" onMouseDown={onCancel}>
            <div role="dialog" aria-modal="true" aria-label={title} className="w-full max-w-sm rounded-xl bg-white p-5 shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
                <h2 className="text-base font-semibold text-gray-800">{title}</h2>
                <p className="mt-2 text-sm text-gray-600">{message}</p>
                <div className="mt-5 flex justify-end gap-2">
                    <button onClick={onCancel} className="rounded-lg border border-gray-200 px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-50">
                        {cancelLabel}
                    </button>
                    <button onClick={onConfirm} className="rounded-lg bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700">
                        {confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}
