import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Play, Clock, CheckCircle, XCircle, ChevronRight } from "lucide-react";
import { useWorkflows } from "../hooks/useWorkflows";
import { useWorkflowStore } from "../store/workflowStore";
import { api } from "../api/client";

export default function Dashboard() {
    const { workflows, isLoading, fetchWorkflows, executeWorkflow } =
        useWorkflows();
    const { executions, setExecutions } = useWorkflowStore();

    useEffect(() => {
        fetchWorkflows();
        fetchExecutions();
    }, []);

    const fetchExecutions = async () => {
        const { data } = await api.getExecutions();
        if (data) setExecutions(data);
    };

    const handleExecute = async (id: number) => {
        const { data, error } = await executeWorkflow(id);
        if (data) {
            alert(`Workflow started! Execution ID: ${data.execution_id}`);
            setTimeout(fetchExecutions, 1000);
        }
        if (error) alert(`Error: ${error}`);
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case "success":
                return <CheckCircle className="w-5 h-5 text-green-500" />;
            case "failed":
                return <XCircle className="w-5 h-5 text-red-500" />;
            case "running":
                return <Clock className="w-5 h-5 text-blue-500 animate-spin" />;
            default:
                return <Clock className="w-5 h-5 text-gray-400" />;
        }
    };

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
                <p className="text-gray-500 mt-1">Manage your AI workflows</p>
            </div>

            <div className="grid grid-cols-4 gap-6">
                {[
                    {
                        label: "Total Workflows",
                        value: workflows.length,
                        color: "blue",
                    },
                    {
                        label: "Running",
                        value: executions.filter((e) => e.status === "running")
                            .length,
                        color: "yellow",
                    },
                    {
                        label: "Successful",
                        value: executions.filter((e) => e.status === "success")
                            .length,
                        color: "green",
                    },
                    {
                        label: "Failed",
                        value: executions.filter((e) => e.status === "failed")
                            .length,
                        color: "red",
                    },
                ].map((stat) => (
                    <div
                        key={stat.label}
                        className="bg-white p-6 rounded-xl border border-gray-200"
                    >
                        <p className="text-sm text-gray-500">{stat.label}</p>
                        <p
                            className={`text-3xl font-bold text-${stat.color}-600 mt-2`}
                        >
                            {stat.value}
                        </p>
                    </div>
                ))}
            </div>

            <div>
                <h2 className="text-xl font-semibold text-gray-900 mb-4">
                    Your Workflows
                </h2>

                {isLoading ? (
                    <div className="text-center py-12 text-gray-500">
                        Loading...
                    </div>
                ) : workflows.length === 0 ? (
                    <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
                        <p className="text-gray-500 mb-4">No workflows yet</p>
                        <Link
                            to="/templates"
                            className="text-blue-600 hover:underline"
                        >
                            Start with a template →
                        </Link>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {workflows.map((workflow) => (
                            <div
                                key={workflow.id}
                                className="bg-white p-6 rounded-xl border border-gray-200 hover:border-blue-300 transition-colors"
                            >
                                <div className="flex items-center justify-between">
                                    <div className="flex-1">
                                        <Link
                                            to={`/workflow/${workflow.id}`}
                                            className="text-lg font-semibold text-gray-900 hover:text-blue-600"
                                        >
                                            {workflow.name}
                                        </Link>
                                        <p className="text-sm text-gray-500 mt-1">
                                            {workflow.description}
                                        </p>
                                        <div className="flex gap-2 mt-3">
                                            {workflow.nodes.map((node) => (
                                                <span
                                                    key={node.id}
                                                    className="px-2 py-1 bg-gray-100 text-xs rounded-md text-gray-600"
                                                >
                                                    {node.type}
                                                </span>
                                            ))}
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-3">
                                        <button
                                            onClick={() =>
                                                handleExecute(workflow.id)
                                            }
                                            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                                        >
                                            <Play className="w-4 h-4" />
                                            Run
                                        </button>
                                        <Link
                                            to={`/workflow/${workflow.id}`}
                                            className="p-2 text-gray-400 hover:text-gray-600"
                                        >
                                            <ChevronRight className="w-5 h-5" />
                                        </Link>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div>
                <h2 className="text-xl font-semibold text-gray-900 mb-4">
                    Recent Executions
                </h2>
                <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                    {executions.slice(0, 5).map((execution) => (
                        <div
                            key={execution.id}
                            className="flex items-center gap-4 px-6 py-4 border-b border-gray-100 last:border-0"
                        >
                            {getStatusIcon(execution.status)}
                            <div className="flex-1">
                                <p className="text-sm font-medium text-gray-900">
                                    Workflow #{execution.workflow_id}
                                </p>
                                <p className="text-xs text-gray-500">
                                    {new Date(
                                        execution.started_at,
                                    ).toLocaleString()}
                                </p>
                            </div>
                            <span
                                className={`px-2 py-1 text-xs rounded-full ${
                                    execution.status === "success"
                                        ? "bg-green-100 text-green-700"
                                        : execution.status === "failed"
                                          ? "bg-red-100 text-red-700"
                                          : "bg-blue-100 text-blue-700"
                                }`}
                            >
                                {execution.status}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
