import { useState } from "react";
import { FlaskConical, Loader2 } from "lucide-react";
import { api } from "../../api/client";
import type { WorkflowNode } from "../../types/workflow";

/** Шаги, которые можно проверить на тестовых данных без отправки чего-либо наружу. */
export const TESTABLE_TYPES = ["text_transform", "condition", "switch", "keyword_switch", "set", "text_input", "text_assemble", "print", "http"];

interface Props {
    node: WorkflowNode;
    /** Результаты шагов из последнего запуска: подставляются как данные предыдущих шагов. */
    lastOutputs: Record<string, unknown>;
    defaultInput: string;
}

function show(value: unknown): string {
    return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/** «Проверить шаг»: выполняет только этот шаг на тестовом тексте и показывает, что он вернёт. */
export default function StepTester({ node, lastOutputs, defaultInput }: Props) {
    const [input, setInput] = useState(defaultInput);
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState<{ output?: unknown; branch?: string | null; error?: string } | null>(null);

    if (!TESTABLE_TYPES.includes(node.type)) return null;
    const hasPreviousData = Object.keys(lastOutputs).length > 0;

    const run = async () => {
        setBusy(true);
        setResult(null);
        const { data, error } = await api.testNode({ id: node.id, type: node.type, config: node.config || {} }, input, lastOutputs);
        setBusy(false);
        setResult(error || !data ? { error: error || "Не удалось проверить шаг" } : { output: data.output, branch: data.branch });
    };

    return (
        <details className="rounded-lg border border-gray-200 bg-gray-50">
            <summary className="flex cursor-pointer items-center gap-1.5 px-3 py-2 text-xs font-medium text-gray-700">
                <FlaskConical className="h-3.5 w-3.5 text-emerald-600" />
                Проверить шаг
            </summary>
            <div className="space-y-2 border-t border-gray-200 p-3">
                <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">Тестовый текст ({"{input}"})</label>
                    <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        rows={2}
                        placeholder="Где мой заказ 1234?"
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="mt-1 text-[11px] text-gray-400">
                        {hasPreviousData
                            ? "Данные предыдущих шагов берутся из последнего запуска сценария."
                            : "Если шаг использует данные других шагов, сначала запустите сценарий целиком: их значения подставятся автоматически."}
                    </p>
                </div>
                <button
                    type="button"
                    onClick={run}
                    disabled={busy}
                    className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
                >
                    {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Проверить
                </button>
                {result?.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{result.error}</p>}
                {result && !result.error && (
                    <div className="space-y-1">
                        <p className="text-[11px] font-medium text-gray-500">Результат шага:</p>
                        <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-white px-3 py-2 text-xs text-gray-800 ring-1 ring-gray-200">
                            {show(result.output) || "(пусто)"}
                        </pre>
                        {result.branch != null && <p className="text-xs text-gray-600">Сценарий пойдёт по ветке: «{result.branch}»</p>}
                    </div>
                )}
            </div>
        </details>
    );
}
