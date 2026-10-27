import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AppLayout from "../../components/AppLayout";
import AdminDashboard from "./AdminDashboard";
import AdminUsers from "./AdminUsers";
import AdminPlans from "./AdminPlans";
import AdminPayments from "./AdminPayments";
import AdminSystem from "./AdminSystem";

const TABS = [
    ["dashboard", AdminDashboard],
    ["users", AdminUsers],
    ["plans", AdminPlans],
    ["payments", AdminPayments],
    ["system", AdminSystem],
] as const;

export default function Admin() {
    const { t } = useTranslation();
    const [params, setParams] = useSearchParams();
    const current = params.get("tab") ?? "dashboard";
    const Active = (TABS.find(([id]) => id === current) ?? TABS[0])[1];

    return (
        <AppLayout>
            <h1 className="text-2xl font-bold text-gray-900">{t("admin.title")}</h1>
            <div className="mt-6 flex gap-1 border-b border-gray-200 overflow-x-auto">
                {TABS.map(([id]) => (
                    <button key={id} onClick={() => setParams({ tab: id })}
                        className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 whitespace-nowrap ${current === id ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"}`}>
                        {t(`admin.tabs.${id}`)}
                    </button>
                ))}
            </div>
            <div className="mt-6"><Active /></div>
        </AppLayout>
    );
}
