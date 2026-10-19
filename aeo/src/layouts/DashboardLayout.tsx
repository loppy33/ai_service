import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import { fetchMe } from "../lib/api";
import { clearProject, clearSession, getToken } from "../lib/auth";

const links = [
    { to: "/overview", label: "Overview", icon: "🏠" },
    { to: "/ai-queries-promotion", label: "AI queries Promotion", icon: "📈" },
    { to: "/queries-research", label: "Queries Research", icon: "🧾" },
    { to: "/add-features", label: "Add features", icon: "🧩" },
    { to: "/api", label: "API", icon: "🛠️" },
    { to: "/help", label: "Help", icon: "❓" },
];

export default function DashboardLayout() {
    const navigate = useNavigate();
    const authorized = !!getToken();
    const [projectName, setProjectName] = useState(() => localStorage.getItem("projectName") || "Project name");

    useEffect(() => {
        if (!authorized) return;
        fetchMe()
            .then((me) => {
                setProjectName(me.projectName);
                localStorage.setItem("projectName", me.projectName);
            })
            .catch(() => {
                if (!getToken()) navigate("/login", { replace: true });
            });
    }, [authorized, navigate]);

    if (!authorized) {
        return <Navigate to="/login" replace />;
    }

    const logout = () => {
        clearSession();
        clearProject();
        navigate("/login", { replace: true });
    };

    return (
        <div className="dash">
            <aside className="sidebar">
                <button className="new-project" onClick={() => navigate("/start")}>
                    + New project
                </button>

                <div className="section-title">{projectName}</div>
                <nav className="nav">
                    {links.map((l) => (
                        <NavLink
                            key={l.to}
                            to={l.to}
                            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                            end
                        >
                            <span className="icon" aria-hidden>{l.icon}</span>
                            <span className="label">{l.label}</span>
                        </NavLink>
                    ))}
                </nav>

                <button className="logout" onClick={logout}>
                    Log out
                </button>

                <div className="brand">
                    <div className="logo">👁️ SeeUinAI</div>
                    <div className="legal">© AEO by Luxeo 2025</div>
                    <div className="links">
                        <a href="#" onClick={(e) => e.preventDefault()}>Privacy Policy</a>
                        <span> · </span>
                        <a href="#" onClick={(e) => e.preventDefault()}>Terms of Use</a>
                    </div>
                </div>
            </aside>

            <main>
                <Outlet />
            </main>
        </div>
    );
}
