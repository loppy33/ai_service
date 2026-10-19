import { useState } from "react";
import { sendContactRequest } from "../../lib/api";

export default function ContactForm({ onSent }: { onSent: () => void }) {
    const [email, setEmail] = useState("");
    const [contact, setContact] = useState("");
    const [name, setName] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitting(true);
        setError(null);
        try {
            await sendContactRequest({ email, contact: contact || undefined, name: name || undefined });
            onSent();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to send request. Try again.");
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <form onSubmit={handleSubmit}>
            <div>
                <input
                    className="input"
                    type="email"
                    placeholder="Email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                />
            </div>
            <div>
                <input
                    className="input"
                    type="text"
                    placeholder="WhatsApp or Telegram number"
                    value={contact}
                    onChange={(e) => setContact(e.target.value)}
                />
            </div>
            <div>
                <input
                    className="input"
                    type="text"
                    placeholder="Name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                />
            </div>

            {error && <p className="form__error">{error}</p>}

            <div>
                <button className="submit__btn" type="submit" disabled={submitting}>
                    {submitting ? "Sending…" : "Submit Request"}
                </button>
            </div>
        </form>
    );
}
