import { create } from "zustand";
import type { Workflow, Execution } from "../types/workflow";

interface WorkflowState {
    workflows: Workflow[];
    currentWorkflow: Workflow | null;
    executions: Execution[];
    isLoading: boolean;
    error: string | null;

    setWorkflows: (workflows: Workflow[]) => void;
    setCurrentWorkflow: (workflow: Workflow | null) => void;
    addWorkflow: (workflow: Workflow) => void;
    setExecutions: (executions: Execution[]) => void;
    addExecution: (execution: Execution) => void;
    setLoading: (loading: boolean) => void;
    setError: (error: string | null) => void;
}

export const useWorkflowStore = create<WorkflowState>((set) => ({
    workflows: [],
    currentWorkflow: null,
    executions: [],
    isLoading: false,
    error: null,

    setWorkflows: (workflows) => set({ workflows }),
    setCurrentWorkflow: (workflow) => set({ currentWorkflow: workflow }),
    addWorkflow: (workflow) =>
        set((state) => ({
            workflows: [...state.workflows, workflow],
        })),
    setExecutions: (executions) => set({ executions }),
    addExecution: (execution) =>
        set((state) => ({
            executions: [execution, ...state.executions],
        })),
    setLoading: (isLoading) => set({ isLoading }),
    setError: (error) => set({ error }),
}));
