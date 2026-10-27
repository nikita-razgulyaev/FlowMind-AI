import type { ReactNode } from "react";
import EditorSidebar from "./canvas/EditorSidebar";

/** Общая оболочка внутренних страниц: боковая панель + прокручиваемое содержимое. */
export default function AppLayout({ children }: { children: ReactNode }) {
    return (
        <div className="flex h-screen bg-gray-50">
            <EditorSidebar />
            <main className="flex-1 min-w-0 overflow-y-auto">
                <div className="max-w-5xl mx-auto px-6 py-8">{children}</div>
            </main>
        </div>
    );
}
