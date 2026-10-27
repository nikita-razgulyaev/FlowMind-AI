import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Workflow } from "lucide-react";
import { Card } from "../common/ui";

export default function AuthLayout({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
    return (
        <div className="min-h-screen bg-gradient-to-b from-slate-50 to-blue-50 flex flex-col items-center justify-center px-4 py-10">
            <Link to="/" className="flex items-center gap-2 mb-6 text-gray-900 font-bold text-xl">
                <span className="w-9 h-9 rounded-xl bg-blue-600 text-white flex items-center justify-center">
                    <Workflow className="w-5 h-5" />
                </span>
                FlowMind AI
            </Link>
            <Card className="w-full max-w-md p-6 sm:p-8">
                <h1 className="text-xl font-bold text-gray-900">{title}</h1>
                {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
                <div className="mt-6">{children}</div>
            </Card>
        </div>
    );
}
