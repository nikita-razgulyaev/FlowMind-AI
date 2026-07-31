import { Routes, Route, Navigate } from "react-router-dom";
import WorkflowList from "./pages/WorkflowList";
import WorkflowEditor from "./pages/WorkflowEditor";
import ExecutionHistory from "./pages/ExecutionHistory";
import Settings from "./pages/Settings";
import Templates from "./pages/Templates";
import Connections from "./pages/Connections";

export default function App() {
    return (
        <Routes>
            <Route path="/" element={<WorkflowList />} />
            <Route path="/executions" element={<ExecutionHistory />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/templates" element={<Templates />} />
            <Route path="/connections" element={<Connections />} />
            <Route path="/workflow/new" element={<WorkflowEditor />} />
            <Route path="/workflow/:id" element={<WorkflowEditor />} />
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    );
}
