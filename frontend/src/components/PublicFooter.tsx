import { useAuth } from "../store/auth";
import ContactsList, { hasContacts } from "./feedback/ContactsList";

/** Футер публичных страниц: копирайт и контакты (если они заданы в настройках сервера). Навигации в футере нет — она в шапке. */
export default function PublicFooter() {
    const contacts = useAuth((s) => s.config?.contacts);

    return (
        <footer className="border-t border-gray-100">
            <div className="max-w-6xl mx-auto px-6 py-8 flex flex-wrap items-center justify-between gap-4 text-sm text-gray-500">
                <span>© {new Date().getFullYear()} FlowMind AI</span>
                {hasContacts(contacts) && <ContactsList contacts={contacts} variant="compact" />}
            </div>
        </footer>
    );
}
