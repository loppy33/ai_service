export function NoResultsStep({
    email,
    name,
    submitting,
    onChangeEmail,
    onChangeName,
    onSubmit,
}: {
    email: string;
    name: string;
    submitting: boolean;
    onChangeEmail: (v: string) => void;
    onChangeName: (v: string) => void;
    onSubmit: () => void;
}) {
    return (
        <div className="response">
            <form
                className="report"
                onSubmit={(e) => {
                    e.preventDefault();
                    onSubmit();
                }}
            >
                <h4>Download report and key visibility recommendations</h4>
                <input
                    className="input"
                    type="email"
                    placeholder="Email (required)"
                    value={email}
                    onChange={(e) => onChangeEmail(e.target.value)}
                    required
                />
                <input
                    className="input"
                    type="text"
                    placeholder="Name (optional)"
                    value={name}
                    onChange={(e) => onChangeName(e.target.value)}
                />
                <button className="submit__btn" type="submit" disabled={submitting}>
                    {submitting ? "Sending…" : "Send"}
                </button>
            </form>
        </div>
    );
}
