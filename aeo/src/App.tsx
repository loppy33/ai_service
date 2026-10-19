import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import Overview from "./pages/Overview";
import Plans from "./pages/Plans";
import Success from "./pages/Success";
import ComingSoon from "./pages/ComingSoon";
import DashboardLayout from "./layouts/DashboardLayout";

const placeholders = [
    { path: "/ai-queries-promotion", title: "AI queries Promotion" },
    { path: "/queries-research", title: "Queries Research" },
    { path: "/add-features", title: "Add features" },
    { path: "/api", title: "API" },
    { path: "/help", title: "Help" },
];

function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/login" element={<Login />} />
                <Route path="/start" element={<Onboarding />} />
                <Route path="/success" element={<Success />} />

                <Route element={<DashboardLayout />}>
                    <Route path="/overview" element={<Overview />} />
                    <Route path="/plans" element={<Plans />} />
                    {placeholders.map((p) => (
                        <Route key={p.path} path={p.path} element={<ComingSoon title={p.title} />} />
                    ))}
                </Route>

                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;
