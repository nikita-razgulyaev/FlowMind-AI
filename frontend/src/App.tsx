import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import WorkflowEditor from "./pages/WorkflowEditor";
import ExecutionLogs from "./pages/ExecutionLogs";
import Templates from "./pages/Templates";

export default function App() {
    return (
        <Layout>
            <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/workflow/new" element={<WorkflowEditor />} />
                <Route path="/workflow/:id" element={<WorkflowEditor />} />
                <Route path="/executions" element={<ExecutionLogs />} />
                <Route path="/templates" element={<Templates />} />
            </Routes>
        </Layout>
    );
}
