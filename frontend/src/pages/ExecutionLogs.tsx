import { useEffect, useState } from "react";
import {
    CheckCircle,
    XCircle,
    Clock,
    ChevronDown,
    ChevronUp,
} from "lucide-react";
import { useWorkflowStore } from "../store/workflowStore";
import { api } from "../api/client";

export default function ExecutionLogs() {
    const { executions, setExecutions } = useWorkflowStore();
    const [expandedId, setExpandedId] = useState<number | null>(null);

    useEffect(() => {
        fetchExecutions();
        const interval = setInterval(fetchExecutions, 3000);
        return () => clearInterval(interval);
    }, []);

    const fetchExecutions = async () => {
        const { data } = await api.getExecutions();
        if (data) setExecutions(data);
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
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold text-gray-900">
                    Execution Logs
                </h1>
                <p className="text-gray-500 mt-1">Monitor your workflow runs</p>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                {executions.length === 0 ? (
                    <div className="p-12 text-center text-gray-500">
                        No executions yet
                    </div>
                ) : (
                    executions.map((execution) => (
                        <div
                            key={execution.id}
                            className="border-b border-gray-100 last:border-0"
                        >
                            <div
                                className="flex items-center gap-4 px-6 py-4 cursor-pointer hover:bg-gray-50"
                                onClick={() =>
                                    setExpandedId(
                                        expandedId === execution.id
                                            ? null
                                            : execution.id,
                                    )
                                }
                            >
                                {getStatusIcon(execution.status)}
                                <div className="flex-1">
                                    <p className="text-sm font-medium text-gray-900">
                                        Execution #{execution.id} — Workflow #
                                        {execution.workflow_id}
                                    </p>
                                    <p className="text-xs text-gray-500">
                                        {new Date(
                                            execution.started_at,
                                        ).toLocaleString()}
                                        {execution.finished_at &&
                                            ` • ${Math.round(
                                                (new Date(
                                                    execution.finished_at,
                                                ).getTime() -
                                                    new Date(
                                                        execution.started_at,
                                                    ).getTime()) /
                                                    1000,
                                            )}s`}
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
                                {expandedId === execution.id ? (
                                    <ChevronUp className="w-5 h-5 text-gray-400" />
                                ) : (
                                    <ChevronDown className="w-5 h-5 text-gray-400" />
                                )}
                            </div>

                            {expandedId === execution.id && execution.logs && (
                                <div className="px-6 pb-4 bg-gray-50">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                                        Step Logs
                                    </h4>
                                    <div className="space-y-2">
                                        {execution.logs.map((log, i) => (
                                            <div
                                                key={i}
                                                className="bg-white border border-gray-200 rounded-lg p-3"
                                            >
                                                <div className="flex items-center gap-2 mb-2">
                                                    <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">
                                                        {log.type}
                                                    </span>
                                                    <span className="text-xs text-gray-400 font-mono">
                                                        {log.node_id}
                                                    </span>
                                                    <span className="text-xs text-gray-400 ml-auto">
                                                        {new Date(
                                                            log.timestamp,
                                                        ).toLocaleTimeString()}
                                                    </span>
                                                </div>
                                                <div className="grid grid-cols-2 gap-4">
                                                    <div>
                                                        <p className="text-xs text-gray-500 mb-1">
                                                            Input
                                                        </p>
                                                        <pre className="text-xs bg-gray-100 p-2 rounded overflow-auto">
                                                            {JSON.stringify(
                                                                log.input,
                                                                null,
                                                                2,
                                                            )}
                                                        </pre>
                                                    </div>
                                                    <div>
                                                        <p className="text-xs text-gray-500 mb-1">
                                                            Output
                                                        </p>
                                                        <pre className="text-xs bg-gray-100 p-2 rounded overflow-auto">
                                                            {typeof log.output ===
                                                            "string"
                                                                ? log.output
                                                                : JSON.stringify(
                                                                      log.output,
                                                                      null,
                                                                      2,
                                                                  )}
                                                        </pre>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    {execution.result && (
                                        <div className="mt-4">
                                            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                                                Final Result
                                            </h4>
                                            <pre className="bg-white border border-gray-200 rounded-lg p-3 text-sm overflow-auto">
                                                {JSON.stringify(
                                                    execution.result,
                                                    null,
                                                    2,
                                                )}
                                            </pre>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
