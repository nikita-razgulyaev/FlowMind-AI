export interface WorkflowNode {
    id: string;
    type:
        | "manual"
        | "telegram_trigger"
        | "schedule"
        | "email_trigger"
        | "email_send"
        | "text_transform"
        | "webhook"
        | "switch"
        | "set"
        | "text_input"
        | "llm"
        | "http"
        | "condition"
        | "print"
        | "agent"
        | "telegram_send"
        | "google_sheets_append"
        | "google_calendar_create_event"
        | "file_read"
        | "file_write";
    config: Record<string, any>;
    position?: { x: number; y: number } | null;
}

export interface WorkflowEdge {
    id: string;
    from_node: string;
    to_node: string;
    condition?: string;
    type?: "next" | "tool";
}

export interface Workflow {
    id: number;
    name: string;
    description: string;
    nodes: WorkflowNode[];
    edges: WorkflowEdge[];
    is_active: boolean;
    is_ai?: boolean;
    has_telegram_trigger?: boolean;
    created_at: string;
}

export interface Execution {
    id: number;
    workflow_id: number;
    status: "pending" | "running" | "success" | "failed";
    source?: "manual" | "telegram" | "webhook" | "schedule" | "email";
    is_ai?: boolean;
    trigger_data: Record<string, any> | null;
    result: Record<string, any> | null;
    logs: ExecutionLog[] | null;
    started_at: string;
    finished_at: string | null;
}

export interface ExecutionLog {
    node_id: string;
    type: string;
    input: Record<string, any>;
    output: any;
    timestamp: string;
}

export interface Template {
    name: string;
    description: string;
    nodes: WorkflowNode[];
    edges: WorkflowEdge[];
}

export interface Connection {
    id: number;
    category: "ai_api" | "tool";
    provider: string;
    name: string;
    config: Record<string, any>;
    oauth?: boolean;
    needs_reauth?: boolean;
    account?: string;
    created_at: string;
}
