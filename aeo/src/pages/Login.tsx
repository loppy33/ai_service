import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import LoginForm from "../components/forms/LoginForm";
import { login, register } from "../lib/api";
import type { AuthResult } from "../lib/api";
import { getToken, setToken } from "../lib/auth";

export default function Login() {
    const navigate = useNavigate();
    const [mode, setMode] = useState<"register" | "login">("register");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [projectName, setProjectName] = useState("");
    const [subscribe, setSubscribe] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    if (getToken() && !submitting) {
        return <Navigate to="/overview" replace />;
    }

    const finish = (auth: AuthResult, isNewUser: boolean) => {
        setToken(auth.token);
        localStorage.setItem("projectName", auth.projectName);
        const hasProject = !!localStorage.getItem("company_name");
        navigate(isNewUser || !hasProject ? "/start" : "/overview", { replace: true });
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setSubmitting(true);
        try {
            if (mode === "register") {
                finish(await register({ email, password, projectName: projectName.trim(), subscribe }), true);
            } else {
                finish(await login({ email, password }), false);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
            setSubmitting(false);
        }
    };

    return (
        <div className="Login">
            <div className="content">
                <h2>{mode === "register" ? "Sign up for access to the dashboard!" : "Log in to your dashboard"}</h2>
                <div className="login__container">
                    <div className="left">
                        <nav>
                            <ul>
                                <li><img src="/images/check.png" alt="" /> Free analytics</li>
                                <li><img src="/images/check.png" alt="" /> Access to a dashboard</li>
                                <li><img src="/images/check.png" alt="" /> 24/7 AI visibility monitoring</li>
                            </ul>
                        </nav>
                    </div>
                    <div className="right">
                        <LoginForm
                            mode={mode}
                            email={email}
                            password={password}
                            projectName={projectName}
                            subscribe={subscribe}
                            submitting={submitting}
                            error={error ?? undefined}
                            onEmailChange={setEmail}
                            onPasswordChange={setPassword}
                            onProjectNameChange={setProjectName}
                            onSubscribeChange={setSubscribe}
                            onToggleMode={() => {
                                setError(null);
                                setMode((m) => (m === "register" ? "login" : "register"));
                            }}
                            onSubmit={handleSubmit}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}
