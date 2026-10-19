import type { LoginFormProps } from "../types";

export default function LoginForm({
    mode,
    email,
    password,
    projectName,
    subscribe,
    submitting,
    error,
    onEmailChange,
    onPasswordChange,
    onProjectNameChange,
    onSubscribeChange,
    onToggleMode,
    onSubmit,
}: LoginFormProps) {
    const isRegister = mode === "register";

    return (
        <form onSubmit={onSubmit}>
            <div>
                <input
                    className="input"
                    type="email"
                    placeholder="Email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => onEmailChange(e.target.value)}
                    required
                />
            </div>
            <div>
                <input
                    className="input"
                    type="password"
                    placeholder="Password"
                    autoComplete={isRegister ? "new-password" : "current-password"}
                    minLength={isRegister ? 8 : undefined}
                    value={password}
                    onChange={(e) => onPasswordChange(e.target.value)}
                    required
                />
            </div>
            {isRegister && (
                <>
                    <div>
                        <input
                            className="input"
                            type="text"
                            placeholder="Project name"
                            value={projectName}
                            onChange={(e) => onProjectNameChange(e.target.value)}
                            required
                        />
                    </div>
                    <div>
                        <label className="checkbox">
                            <input
                                type="checkbox"
                                checked={subscribe}
                                onChange={(e) => onSubscribeChange(e.target.checked)}
                            />
                            Subscribe to our newsletter
                        </label>
                    </div>
                </>
            )}
            {error && <p className="form__error">{error}</p>}
            <div>
                <button className="submit__btn" type="submit" disabled={!!submitting}>
                    {submitting ? "Please wait…" : isRegister ? "Submit" : "Log in"}
                </button>
                <p>
                    {isRegister ? "Already have an account? " : "No account yet? "}
                    <a
                        href="#"
                        onClick={(e) => {
                            e.preventDefault();
                            onToggleMode();
                        }}
                    >
                        {isRegister ? "Log in!" : "Sign up!"}
                    </a>
                </p>
            </div>
        </form>
    );
}
