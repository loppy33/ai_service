export function ClarifyStep({
    value,
    onChange,
    onSend,
}: {
    value: string;
    onChange: (v: string) => void;
    onSend: () => void;
}) {
    return (
        <div className="response user clarify">
            <div className="enter__container">
                <div className="input">
                    <input
                        type="text"
                        placeholder="Tell me about your company..."
                        value={value}
                        onChange={(e) => onChange(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") onSend();
                        }}
                    />
                    <button onClick={onSend}>
                        <img src="/images/send.png" alt="Send" />
                    </button>
                </div>
            </div>
        </div>
    );
}
