export interface WorkflowNode {
    id: string;
    type:
        | "manual"
        | "schedule"
        | "llm"
        | "http"
        | "condition"
        | "print"
        | "agent"
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
    created_at: string;
}

export interface Execution {
    id: number;
    workflow_id: number;
    status: "pending" | "running" | "success" | "failed";
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