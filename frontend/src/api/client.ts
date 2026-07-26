import type { Workflow } from "../types/workflow";

const API_BASE = "/api";

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
            // Извлекаем сообщение об ошибке
            let errorMsg = "Unknown error";
            if (typeof data.detail === "string") {
                errorMsg = data.detail;
            } else if (typeof data.error === "string") {
                errorMsg = data.error;
            } else if (data.detail) {
                errorMsg = JSON.stringify(data.detail);
            } else {
                errorMsg = JSON.stringify(data);
            }
            return { data: null as any, error: errorMsg };
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

    async updateWorkflow(
        id: number,
        workflow: Omit<Workflow, "id" | "created_at">,
    ): Promise<ApiResponse<Workflow>> {
        return this.request(`/workflows/${id}`, {
            method: "PUT",
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

    async getExecutions(workflowId?: number): Promise<ApiResponse<any[]>> {
        const query = workflowId ? `?workflow_id=${workflowId}` : "";
        return this.request(`/executions/${query}`);
    }

    async getExecution(id: number): Promise<ApiResponse<any>> {
        return this.request(`/executions/${id}`);
    }

    async getTemplates(): Promise<ApiResponse<Record<string, any>>> {
        return this.request("/templates/");
    }
}

export const api = new ApiClient();
