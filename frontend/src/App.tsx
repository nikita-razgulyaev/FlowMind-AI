import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./store/auth";
import { Spinner } from "./components/common/ui";
import { GuestOnly, HomeGate, RequireAdmin, RequireAuth } from "./components/auth/guards";
import WorkflowEditor from "./pages/WorkflowEditor";
import ExecutionHistory from "./pages/ExecutionHistory";
import Templates from "./pages/Templates";
import Connections from "./pages/Connections";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import Register from "./pages/Register";
import { ForgotPassword, ResetPassword, VerifyEmail } from "./pages/PasswordPages";
import Pricing from "./pages/Pricing";
import Landing from "./pages/Landing";
import Checkout from "./pages/Checkout";
import BillingReturn from "./pages/BillingReturn";
import Account from "./pages/Account";
import Admin from "./pages/admin/Admin";

/** Прокрутка при переходах: к якорю (#features), иначе — наверх. Нужна, потому что это SPA без перезагрузок страницы. */
function ScrollManager() {
    const { pathname, hash } = useLocation();
    useEffect(() => {
        if (hash) {
            const element = document.getElementById(hash.slice(1));
            if (element) {
                element.scrollIntoView({ behavior: "smooth", block: "start" });
                return;
            }
        }
        window.scrollTo(0, 0);
    }, [pathname, hash]);
    return null;
}

export default function App() {
    const { ready, bootstrap } = useAuth();
    useEffect(() => { void bootstrap(); }, []);
    if (!ready) return <Spinner />;

    return (
        <>
            <ScrollManager />
            <Routes>
                <Route path="/" element={<HomeGate />} />
                <Route path="/about" element={<Landing />} />
                <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
                <Route path="/register" element={<GuestOnly><Register /></GuestOnly>} />
                <Route path="/forgot-password" element={<ForgotPassword />} />
                <Route path="/reset-password" element={<ResetPassword />} />
                <Route path="/verify-email" element={<VerifyEmail />} />
                <Route path="/pricing" element={<Pricing />} />

                <Route path="/workflow/new" element={<RequireAuth><WorkflowEditor /></RequireAuth>} />
                <Route path="/workflow/:id" element={<RequireAuth><WorkflowEditor /></RequireAuth>} />
                <Route path="/executions" element={<RequireAuth><ExecutionHistory /></RequireAuth>} />
                <Route path="/templates" element={<RequireAuth><Templates /></RequireAuth>} />
                <Route path="/connections" element={<RequireAuth><Connections /></RequireAuth>} />
                <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
                <Route path="/account" element={<RequireAuth><Account /></RequireAuth>} />
                <Route path="/checkout" element={<RequireAuth><Checkout /></RequireAuth>} />
                <Route path="/billing/return" element={<RequireAuth><BillingReturn /></RequireAuth>} />
                <Route path="/admin" element={<RequireAdmin><Admin /></RequireAdmin>} />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </>
    );
}
