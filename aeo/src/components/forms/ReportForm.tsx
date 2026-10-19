import type { ReportFormProps } from "../types";

export default function ReportForm({
    email,
    name,
    onEmailChange,
    onNameChange,
    onSubmit,
    submitting,
    error,
}: ReportFormProps) {
    return (
        <form onSubmit={onSubmit}>
            <div>
                <input
                    autoFocus
                    className="input"
                    type="email"
                    placeholder="Email"
                    value={email}
                    onChange={(e) => onEmailChange(e.target.value)}
                    required
                />
            </div>
            <div>
                <input
                    className="input"
                    type="text"
                    placeholder="Name (optional)"
                    value={name}
                    onChange={(e) => onNameChange(e.target.value)}
                />
            </div>

            {error && <p className="form__error">{error}</p>}

            <div>
                <button className="submit__btn" type="submit" disabled={!!submitting}>
                    {submitting ? "Sending…" : "Download"}
                </button>
            </div>
        </form>
    );
}
