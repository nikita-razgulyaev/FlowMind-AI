import { useTranslation } from "react-i18next";
import { useAuth } from "../store/auth";
import PublicHeader from "../components/PublicHeader";
import PublicFooter from "../components/PublicFooter";
import ContactsList, { hasContacts } from "../components/feedback/ContactsList";
import FeedbackForm from "../components/feedback/FeedbackForm";
import { Card } from "../components/common/ui";

/** Публичная страница /contacts: контакты из настроек сервера и форма обратной связи. */
export default function Contacts() {
    const { t } = useTranslation();
    const config = useAuth((s) => s.config);
    const showForm = !!config?.feedback_enabled;
    const showContacts = hasContacts(config?.contacts);

    return (
        <div className="min-h-screen flex flex-col bg-white">
            <PublicHeader />
            <main className="flex-1">
                <div className="max-w-3xl mx-auto px-6 py-12 space-y-10">
                    <header>
                        <h1 className="text-3xl font-bold text-gray-900">{t("contacts.title")}</h1>
                        <p className="mt-2 text-gray-500">{t("contacts.subtitle")}</p>
                    </header>

                    {showContacts && <ContactsList contacts={config?.contacts} variant="card" />}
                    {!showContacts && !showForm && <p className="text-sm text-gray-500">{t("contacts.empty")}</p>}

                    {showForm && (
                        <section aria-labelledby="contact-form-title">
                            <h2 id="contact-form-title" className="mb-4 text-xl font-semibold text-gray-800">{t("contacts.formTitle")}</h2>
                            <Card className="p-6">
                                <FeedbackForm />
                            </Card>
                        </section>
                    )}
                </div>
            </main>
            <PublicFooter />
        </div>
    );
}
