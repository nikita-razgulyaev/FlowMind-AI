import type { Workflow, Connection } from "../types/workflow";
import type {
    AiChatMessage, AppConfig, CardInput, MeResponse, Payment, Period, Plan, Quote, Subscription, User,
} from "../types/app";

const API_BASE = "/api";

export interface ApiResponse<T> {
    data: T;
    error?: string;
    code?: string;
    status?: number;
}

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;
let onSessionLost: (() => void) | null = null;

export function setAccessToken(token: string | null) {
    accessToken = token;
}

export function setSessionLostHandler(handler: () => void) {
    onSessionLost = handler;
}

function extractError(data: any, status?: number): { message: string; code?: string } {
    const detail = data?.detail;
    if (typeof detail === "string") return { message: detail };
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
        return { message: detail.message ?? JSON.stringify(detail), code: detail.code };
    }
    if (Array.isArray(detail) && detail.length) {
        // ошибки валидации FastAPI/Pydantic
        const first = detail[0];
        const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : "";
        return { message: `${field ? field + ": " : ""}${first.msg ?? "Некорректные данные"}`, code: "validation_error" };
    }
    if (typeof data?.error === "string") return { message: data.error };
    // 502/503/504 от прокси (Render, Caddy) — тело часто HTML или пустое
    if (status === 502 || status === 503 || status === 504) {
        return {
            message: "Сервер временно недоступен. Подождите 30–60 секунд и обновите страницу (на бесплатном тарифе сервис «засыпает» после простоя).",
            code: "server_unavailable",
        };
    }
    if (status !== undefined && status >= 500) {
        return { message: "Внутренняя ошибка сервера. Попробуйте ещё раз через минуту.", code: "server_error" };
    }
    return { message: "Неизвестная ошибка" };
}

async function rawRequest(endpoint: string, options: RequestInit): Promise<Response> {
    const headers: Record<string, string> = { "Content-Type": "application/json", ...(options.headers as any) };
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    return fetch(`${API_BASE}${endpoint}`, { ...options, headers, credentials: "same-origin" });
}

export async function refreshSession(): Promise<boolean> {
    if (!refreshInFlight) {
        refreshInFlight = (async () => {
            try {
                const res = await fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "same-origin" });
                if (!res.ok) return false;
                const data = await res.json();
                accessToken = data.access_token;
                return true;
            } catch {
                return false;
            } finally {
                setTimeout(() => (refreshInFlight = null), 0);
            }
        })();
    }
    return refreshInFlight;
}

async function request<T>(endpoint: string, options: RequestInit = {}, retry = true): Promise<ApiResponse<T>> {
    let response: Response;
    try {
        response = await rawRequest(endpoint, options);
    } catch {
        return { data: null as any, error: "Нет соединения с сервером", code: "network_error" };
    }

    if (response.status === 401 && retry && !endpoint.startsWith("/auth/")) {
        if (await refreshSession()) return request<T>(endpoint, options, false);
        accessToken = null;
        onSessionLost?.();
    }

    let data: any = null;
    try {
        data = await response.json();
    } catch {
        /* пустое тело */
    }

    if (!response.ok) {
        const { message, code } = extractError(data, response.status);
        return { data: null as any, error: message, code, status: response.status };
    }
    return { data, status: response.status };
}

const json = (method: string, body?: unknown): RequestInit => ({
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
});

class ApiClient {
    // ───── система / авторизация ─────
    getConfig() { return request<AppConfig>("/config"); }

    login(email: string, password: string) {
        return request<{ access_token: string; user: User }>("/auth/login", json("POST", { email, password }));
    }
    register(email: string, password: string, name: string) {
        return request<{ verification_required: boolean; dev_link?: string | null; access_token?: string; user?: User }>(
            "/auth/register", json("POST", { email, password, name }));
    }
    logout() { return request<{ ok: boolean }>("/auth/logout", json("POST")); }
    verifyEmail(token: string) {
        return request<{ access_token: string; user: User }>("/auth/verify-email", json("POST", { token }));
    }
    resendVerification(email: string) {
        return request<{ ok: boolean; dev_link?: string | null }>("/auth/resend-verification", json("POST", { email }));
    }
    forgotPassword(email: string) {
        return request<{ ok: boolean; dev_link?: string | null }>("/auth/forgot-password", json("POST", { email }));
    }
    resetPassword(token: string, password: string) {
        return request<{ ok: boolean }>("/auth/reset-password", json("POST", { token, password }));
    }

    // ───── профиль ─────
    getMe() { return request<MeResponse>("/me"); }
    updateProfile(name: string) { return request<User>("/me", json("PATCH", { name })); }
    changePassword(current_password: string, new_password: string) {
        return request<{ ok: boolean }>("/me/password", json("POST", { current_password, new_password }));
    }
    deleteAccount(password: string) { return request<{ ok: boolean }>("/me", json("DELETE", { password })); }
    getUserSettings() { return request<Record<string, any>>("/me/settings"); }
    saveUserSettings(settings: Record<string, any>) { return request<Record<string, any>>("/me/settings", json("PUT", settings)); }

    // ───── воркфлоу ─────
    getWorkflows() { return request<Workflow[]>("/workflows/"); }
    getWorkflow(id: number) { return request<Workflow>(`/workflows/${id}`); }
    createWorkflow(workflow: Omit<Workflow, "id" | "created_at">) { return request<Workflow>("/workflows/", json("POST", workflow)); }
    updateWorkflow(id: number, workflow: Omit<Workflow, "id" | "created_at">) {
        return request<Workflow>(`/workflows/${id}`, json("PUT", workflow));
    }
    deleteWorkflow(id: number) { return request<{ message: string }>(`/workflows/${id}`, json("DELETE")); }
    bulkDeleteWorkflows(ids: number[]) { return request<{ deleted: number }>("/workflows/bulk-delete", json("POST", { ids })); }
    bulkDeleteExecutions(ids: number[]) { return request<{ deleted: number }>("/executions/bulk-delete", json("POST", { ids })); }
    executeWorkflow(id: number, triggerData?: Record<string, any>) {
        return request<{ execution_id: number; status: string; result: any }>(
            `/workflows/${id}/execute`, json("POST", triggerData || {}));
    }
    createFromTemplate(templateName: string) { return request<Workflow>(`/workflows/from-template/${templateName}`, json("POST")); }
    getExecutions(workflowId?: number) {
        return request<any[]>(`/executions${workflowId ? `?workflow_id=${workflowId}` : ""}`);
    }
    getExecution(id: number) { return request<any>(`/executions/${id}`); }
    getTemplates() { return request<Record<string, any>>("/templates"); }

    // ───── подключения ─────
    getConnections(category?: "ai_api" | "tool") {
        return request<Connection[]>(`/connections${category ? `?category=${category}` : ""}`);
    }
    createConnection(connection: Omit<Connection, "id" | "created_at">) {
        return request<Connection>("/connections", json("POST", connection));
    }
    deleteConnection(id: number) { return request<{ deleted: number }>(`/connections/${id}`, json("DELETE")); }
    startGoogleOAuth(provider: string, name: string) {
        return request<{ auth_url: string }>(
            `/oauth/google/start?provider=${encodeURIComponent(provider)}&name=${encodeURIComponent(name)}`);
    }

    // ───── Telegram ─────
    getTelegramStatus() {
        return request<{ mode: string; public_url_configured: boolean; connections: { id: number; name: string; webhook_registered: boolean }[] }>("/telegram/status");
    }
    syncTelegram() { return request<{ mode: string; results: any[] }>("/telegram/sync", json("POST")); }

    // ───── AI-чат ─────
    aiChat(messages: AiChatMessage[], workflow: { nodes: any[]; edges: any[] } | null, connectionId?: number | null) {
        return request<{ reply: string; workflow: { nodes: any[]; edges: any[] } | null }>(
            "/ai/chat", json("POST", { messages, workflow, connection_id: connectionId ?? null }));
    }

    // ───── тарифы и оплата ─────
    getPlans() { return request<Plan[]>("/plans"); }
    getSubscription() { return request<Subscription>("/billing/subscription"); }
    quote(plan_code: string, period: Period) { return request<Quote>("/billing/quote", json("POST", { plan_code, period })); }
    checkout(plan_code: string, period: Period) {
        return request<{ action: string; payment?: Payment; effective_at?: string | null }>(
            "/billing/checkout", json("POST", { plan_code, period }));
    }
    cancelSubscription() { return request<{ action: string }>("/billing/cancel", json("POST")); }
    getPayments() { return request<Payment[]>("/billing/payments"); }
    getPayment(id: number) { return request<Payment>(`/billing/payments/${id}`); }
    getTestCards() { return request<{ number: string; result: string }[]>("/billing/test-cards"); }
    mockPay(id: number, card: CardInput) { return request<Payment>(`/billing/mock/${id}/pay`, json("POST", card)); }
    mockConfirm3ds(id: number, approve: boolean) {
        return request<Payment>(`/billing/mock/${id}/confirm-3ds`, json("POST", { approve }));
    }
    demoRenewNow() { return request<{ outcome: Record<string, number>; subscription: Subscription }>("/billing/demo/renew-now", json("POST")); }
    demoFailNext() { return request<Subscription>("/billing/demo/fail-next", json("POST")); }

    // ───── админка ─────
    adminStats() { return request<any>("/admin/stats"); }
    adminUsers(q = "", offset = 0) {
        return request<{ total: number; items: any[] }>(`/admin/users?q=${encodeURIComponent(q)}&offset=${offset}&limit=25`);
    }
    adminUser(id: number) { return request<any>(`/admin/users/${id}`); }
    adminPatchUser(id: number, body: Record<string, any>) { return request<any>(`/admin/users/${id}`, json("PATCH", body)); }
    adminGrant(id: number, body: { plan_code: string; period: Period; days?: number }) {
        return request<Subscription>(`/admin/users/${id}/grant`, json("POST", body));
    }
    adminPlans() { return request<Plan[]>("/admin/plans"); }
    adminUpdatePlan(code: string, body: Record<string, any>) { return request<Plan>(`/admin/plans/${code}`, json("PUT", body)); }
    adminPayments(status = "") { return request<Payment[]>(`/admin/payments?status=${status}`); }
    adminSettings() { return request<{ ai_enabled: boolean; ai_daily_cap: number }>("/admin/settings"); }
    adminSaveSettings(body: Record<string, any>) { return request<{ ai_enabled: boolean; ai_daily_cap: number }>("/admin/settings", json("PUT", body)); }
    adminAudit() { return request<any[]>("/admin/audit"); }
}

export const api = new ApiClient();
