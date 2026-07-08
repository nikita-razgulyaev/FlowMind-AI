import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { api } from "../api/client";
import type { Template } from "../types/workflow";

export default function Templates() {
    const [templates, setTemplates] = useState<Record<string, Template>>({});
    const [isLoading, setIsLoading] = useState(true);
    const navigate = useNavigate();

    useEffect(() => {
        loadTemplates();
    }, []);

    const loadTemplates = async () => {
        const { data } = await api.getTemplates();
        if (data) setTemplates(data);
        setIsLoading(false);
    };

    const useTemplate = async (name: string) => {
        const { data, error } = await api.createFromTemplate(name);
        if (data) {
            navigate(`/workflow/${data.id}`);
        }
        if (error) alert(`Error: ${error}`);
    };

    const templateIcons: Record<string, string> = {
        email_responder: "📧",
        news_summarizer: "📰",
        weather_advisor: "🌤️",
    };

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold text-gray-900">Templates</h1>
                <p className="text-gray-500 mt-1">
                    Start with a pre-built workflow
                </p>
            </div>

            {isLoading ? (
                <div className="text-center py-12">Loading...</div>
            ) : (
                <div className="grid grid-cols-3 gap-6">
                    {Object.entries(templates).map(([key, template]) => (
                        <div
                            key={key}
                            className="bg-white p-6 rounded-xl border border-gray-200 hover:border-blue-300 transition-all hover:shadow-lg"
                        >
                            <div className="text-4xl mb-4">
                                {templateIcons[key] || "🤖"}
                            </div>
                            <h3 className="text-lg font-semibold text-gray-900">
                                {template.name}
                            </h3>
                            <p className="text-sm text-gray-500 mt-2">
                                {template.description}
                            </p>

                            <div className="mt-4 flex gap-2 flex-wrap">
                                {template.nodes.map((node) => (
                                    <span
                                        key={node.id}
                                        className="px-2 py-1 bg-gray-100 text-xs rounded-md text-gray-600"
                                    >
                                        {node.type}
                                    </span>
                                ))}
                            </div>

                            <button
                                onClick={() => useTemplate(key)}
                                className="mt-6 w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                            >
                                <Sparkles className="w-4 h-4" />
                                Use Template
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
