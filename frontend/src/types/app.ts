export type Period = "month" | "year";
export type PlanCode = "free" | "pro" | "business" | "local";

export interface AppConfig {
    deployment_mode: "local" | "cloud";
    auth_required: boolean;
    payment_provider: "mock" | "yookassa";
    demo_mode: boolean;
    require_email_verification: boolean;
    default_llm_mode: "local" | "cloud";
    ollama_model: string;
    platform_ai_available: boolean;
    telegram_mode: "webhook" | "polling" | "off";
    languages: string[];
}

export interface User {
    id: number;
    email: string;
    name: string;
    role: "user" | "admin";
    email_verified: boolean;
    is_local: boolean;
    created_at: string;
}

export interface PlanLimits {
    ai_workflows: number | null;
    regular_workflows: number | null;
    ai_run: number | null;
    regular_run: number | null;
    telegram_triggers: number | null;
    history_days: number | null;
    ai_chat: number | null;
}

export interface Plan {
    code: PlanCode;
    name: string;
    description: string;
    currency: string;
    price_month: number; // копейки
    price_year: number; // копейки, за год
    features: string[];
    sort_order: number;
    is_public: boolean;
    limits: PlanLimits;
}

export interface Subscription {
    plan_code: PlanCode;
    effective_plan: PlanCode;
    period: Period | null;
    status: "active" | "past_due";
    current_period_start: string | null;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    pending_plan_code: PlanCode | null;
    pending_period: Period | null;
    payment_method_label: string | null;
    provider: string | null;
    amount_paid: number;
}

export interface Usage {
    ai_run: number;
    regular_run: number;
    ai_chat: number;
}

export interface MeResponse {
    user: User;
    plan: Plan;
    subscription: Subscription;
    usage: Usage;
    workflows: { ai_workflows: number; regular_workflows: number; telegram_triggers: number };
}

export interface Payment {
    id: number;
    provider: string;
    plan_code: PlanCode;
    period: Period;
    kind: "initial" | "upgrade" | "renewal";
    amount: number;
    plan_price: number;
    currency: string;
    status: "pending" | "requires_action" | "succeeded" | "failed" | "canceled";
    failure_reason: string | null;
    confirmation_url: string | null;
    created_at: string;
    paid_at: string | null;
    card?: { brand: string; last4: string } | null;
    user_email?: string | null;
}

export interface Quote {
    action: "pay" | "schedule" | "cancel" | "resume";
    kind: "initial" | "upgrade";
    price: number;
    credit: number;
    amount: number;
    plan: Plan;
    period: Period;
    effective_at: string | null;
}

export interface CardInput {
    number: string;
    exp_month: number;
    exp_year: number;
    cvc: string;
    holder: string;
}

export interface AiChatMessage {
    role: "user" | "assistant";
    content: string;
}
