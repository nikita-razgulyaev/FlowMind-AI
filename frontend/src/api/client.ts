const API_BASE = "http://localhost:8000";

export interface ApiResponse<T> {
    data: T;
    error?: string;
}

class ApiClient {
    private async request<T>(
        endpoint: string,
        options: RequestInit = {},
    ): Promise<ApiResponse<T>> {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                ...options.headers,
            },
        });

        const data = await response.json();

        if (!response.ok) {
            return { data: null as any, error: data.detail || "Unknown error" };
        }

        return { data };
    }

    async getWorkflows(): Promise<ApiResponse<Workflow[]>> {
        return this.request("/workflows/");
    }

    async getWorkflow(id: number): Promise<ApiResponse<Workflow>> {
        return this.request(`/workflows/${id}`);
    }

    async createWorkflow(
        workflow: Omit<Workflow, "id" | "created_at">,
    ): Promise<ApiResponse<Workflow>> {
        return this.request("/workflows/", {
            method: "POST",
            body: JSON.stringify(workflow),
        });
    }

    async executeWorkflow(
        id: number,
        triggerData?: Record<string, any>,
    ): Promise<ApiResponse<{ execution_id: number; status: string }>> {
        return this.request(`/workflows/${id}/execute`, {
            method: "POST",
            body: JSON.stringify(triggerData || {}),
        });
    }

    async createFromTemplate(
        templateName: string,
    ): Promise<ApiResponse<{ id: number; template: string }>> {
        return this.request(`/workflows/from-template/${templateName}`, {
            method: "POST",
        });
    }

    async getExecutions(
        workflowId?: number,
    ): Promise<ApiResponse<Execution[]>> {
        const query = workflowId ? `?workflow_id=${workflowId}` : "";
        return this.request(`/executions/${query}`);
    }

    async getExecution(id: number): Promise<ApiResponse<Execution>> {
        return this.request(`/executions/${id}`);
    }

    async getTemplates(): Promise<ApiResponse<Record<string, Template>>> {
        return this.request("/templates/");
    }
}

export const api = new ApiClient();
