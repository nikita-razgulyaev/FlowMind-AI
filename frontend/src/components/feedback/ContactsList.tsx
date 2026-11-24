import { Mail, Send, Users } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { AppConfig, Contacts } from "../../types/app";

interface Props {
    contacts: Contacts | undefined;
    /** compact — строкой для футера и модального окна; card — крупными блоками для страницы контактов */
    variant?: "compact" | "card";
}

/** Есть ли что показывать: незаполненные контакты в настройках сервера просто отсутствуют. */
export function hasContacts(contacts: Contacts | undefined): boolean {
    return !!contacts && !!(contacts.email || contacts.telegram || contacts.vk);
}

/**
 * Куда вести пункт «Написать нам» в шапке: к блоку с формой на лендинге, а если формы нет — на страницу /contacts.
 * null — показывать нечего, ссылку не рисуем.
 */
export function contactsLink(config: Pick<AppConfig, "feedback_enabled" | "contacts"> | null | undefined): string | null {
    if (config?.feedback_enabled) return "/about#contact";
    return hasContacts(config?.contacts) ? "/contacts" : null;
}

export default function ContactsList({ contacts, variant = "card" }: Props) {
    const { t } = useTranslation();
    if (!contacts || !hasContacts(contacts)) return null;

    const items: { key: string; icon: ReactNode; title: string; text: string; href: string; external: boolean }[] = [];
    if (contacts.email) items.push({ key: "email", icon: <Mail className="w-4 h-4" />, title: t("contacts.email"), text: contacts.email, href: `mailto:${contacts.email}`, external: false });
    if (contacts.telegram) items.push({ key: "telegram", icon: <Send className="w-4 h-4" />, title: t("contacts.telegram"), text: contacts.telegram.label, href: contacts.telegram.url, external: true });
    if (contacts.vk) items.push({ key: "vk", icon: <Users className="w-4 h-4" />, title: t("contacts.vk"), text: contacts.vk.label, href: contacts.vk.url, external: true });

    const linkProps = (external: boolean) => (external ? { target: "_blank", rel: "noopener noreferrer" } : {});

    if (variant === "compact") {
        return (
            <ul className="flex flex-wrap gap-x-5 gap-y-2" aria-label={t("contacts.title")}>
                {items.map((item) => (
                    <li key={item.key}>
                        <a href={item.href} {...linkProps(item.external)} className="inline-flex items-center gap-1.5 text-sm text-gray-600 hover:text-blue-600">
                            {item.icon}
                            {item.text}
                        </a>
                    </li>
                ))}
            </ul>
        );
    }

    return (
        <div className="space-y-3">
            <ul className="grid gap-3 sm:grid-cols-2">
                {items.map((item) => (
                    <li key={item.key}>
                        <a
                            href={item.href}
                            {...linkProps(item.external)}
                            className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 hover:border-blue-300 hover:shadow-sm transition"
                        >
                            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">{item.icon}</span>
                            <span className="min-w-0">
                                <span className="block text-xs text-gray-400">{item.title}</span>
                                <span className="block truncate text-sm font-medium text-gray-800">{item.text}</span>
                            </span>
                        </a>
                    </li>
                ))}
            </ul>
        </div>
    );
}
