import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../../store/auth";
import { Spinner } from "../common/ui";
import Landing from "../../pages/Landing";
import WorkflowList from "../../pages/WorkflowList";

/** Доступ только для вошедших. В локальной версии (auth_required=false) пускает всех. */
export function RequireAuth({ children }: { children: ReactNode }) {
    const { ready, me } = useAuth();
    const location = useLocation();
    if (!ready) return <Spinner />;
    if (!me) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
    return <>{children}</>;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
    const { ready, me } = useAuth();
    if (!ready) return <Spinner />;
    if (me?.user.role !== "admin") return <Navigate to="/" replace />;
    return <>{children}</>;
}

/** Только для гостей (логин/регистрация): вошедшего отправляет в приложение. */
export function GuestOnly({ children }: { children: ReactNode }) {
    const { ready, me } = useAuth();
    if (!ready) return <Spinner />;
    if (me) return <Navigate to="/" replace />;
    return <>{children}</>;
}

/** «/» — список воркфлоу для вошедшего, лендинг для гостя. */
export function HomeGate() {
    const { ready, me } = useAuth();
    if (!ready) return <Spinner />;
    return me ? <WorkflowList /> : <Landing />;
}
