import { Link, useLocation } from "react-router-dom";
import { Brain, FileText, Play, Plus } from "lucide-react";
import type { ReactNode } from "react";

interface LayoutProps {
    children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
    const location = useLocation();

    const navItems = [
        { path: "/", icon: Brain, label: "Dashboard" },
        { path: "/templates", icon: FileText, label: "Templates" },
        { path: "/executions", icon: Play, label: "Executions" },
    ];

    return (
        <div className="min-h-screen bg-gray-50">
            <aside className="fixed left-0 top-0 h-full w-64 bg-white border-r border-gray-200">
                <div className="p-6">
                    <Link to="/" className="flex items-center gap-3">
                        <Brain className="w-8 h-8 text-blue-600" />
                        <span className="text-xl font-bold text-gray-900">
                            FlowMind
                        </span>
                    </Link>
                </div>

                <nav className="px-4 space-y-1">
                    {navItems.map((item) => {
                        const Icon = item.icon;
                        const isActive = location.pathname === item.path;

                        return (
                            <Link
                                key={item.path}
                                to={item.path}
                                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                                    isActive
                                        ? "bg-blue-50 text-blue-700"
                                        : "text-gray-600 hover:bg-gray-50"
                                }`}
                            >
                                <Icon className="w-5 h-5" />
                                <span className="font-medium">
                                    {item.label}
                                </span>
                            </Link>
                        );
                    })}
                </nav>

                <div className="absolute bottom-6 left-4 right-4">
                    <Link
                        to="/workflow/new"
                        className="flex items-center justify-center gap-2 w-full bg-blue-600 text-white py-3 rounded-lg hover:bg-blue-700 transition-colors"
                    >
                        <Plus className="w-5 h-5" />
                        <span>New Workflow</span>
                    </Link>
                </div>
            </aside>

            <main className="ml-64 p-8">{children}</main>
        </div>
    );
}
