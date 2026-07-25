import { useEffect } from "react";
import { api } from "../api/client";
import { useWorkflowStore } from "../store/workflowStore";
import type { Workflow } from "../types/workflow";

export function useWorkflows() {
    const { workflows, isLoading, error, setWorkflows, setLoading, setError } =
        useWorkflowStore();

    useEffect(() => {
        fetchWorkflows();
    }, []);

    const fetchWorkflows = async () => {
        setLoading(true);
        setError(null);

        const { data, error: apiError } = await api.getWorkflows();

        if (apiError) {
            setError(apiError);
        } else {
            setWorkflows(data);
        }

        setLoading(false);
    };

    const createWorkflow = async (
        workflow: Omit<Workflow, "id" | "created_at">,
    ) => {
        setLoading(true);
        const { data, error: apiError } = await api.createWorkflow(workflow);

        if (!apiError && data) {
            useWorkflowStore.getState().addWorkflow(data);
        }

        setLoading(false);
        return { data, error: apiError };
    };

    const executeWorkflow = async (
        id: number,
        triggerData?: Record<string, any>,
    ) => {
        return api.executeWorkflow(id, triggerData);
    };

    return {
        workflows,
        isLoading,
        error,
        fetchWorkflows,
        createWorkflow,
        executeWorkflow,
    };
}
