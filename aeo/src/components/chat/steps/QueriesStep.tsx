import { useMemo, useRef, useState } from "react";
import type { SuggestedQuery } from "../types";

const MAX_EXTRA = 5;

const normalize = (s: string) => s.toLowerCase().trim().replace(/\s+/g, " ");

export function QueriesStep({
    suggestions,
    selectedQueries,
    onToggleQuery,
    extraQueries,
    onAddExtraQuery,
    onGetResults,
}: {
    suggestions: SuggestedQuery[];
    selectedQueries: string[];
    onToggleQuery: (q: string, checked: boolean) => void;
    extraQueries: string[];
    onAddExtraQuery: (q: string) => void;
    onGetResults: () => Promise<void> | void;
}) {
    const [loading, setLoading] = useState(false);
    const inputRef = useRef<HTMLInputElement | null>(null);

    const selectedCount = selectedQueries.length + extraQueries.length;
    const extraFull = extraQueries.length >= MAX_EXTRA;

    const uniqueSuggested = useMemo(() => {
        const map = new Map<string, SuggestedQuery>();
        for (const item of suggestions) {
            const key = normalize(item.query);
            if (!map.has(key)) map.set(key, item);
        }
        return Array.from(map.values());
    }, [suggestions]);

    const handleAddExtra = () => {
        const input = inputRef.current;
        const value = (input?.value || "").trim();
        if (!input || !value || extraFull) return;

        const norm = normalize(value);
        const duplicate =
            selectedQueries.some((q) => normalize(q) === norm) || extraQueries.some((q) => normalize(q) === norm);
        if (!duplicate) onAddExtraQuery(value);
        input.value = "";
    };

    const handleGetResults = async () => {
        if (loading) return;
        setLoading(true);
        try {
            await onGetResults();
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="response user">
            <div className="phrase__container">
                {!loading && (
                    <>
                        <div className="phrases">
                            {uniqueSuggested.map((q) => {
                                const isSelected = selectedQueries.some((sq) => normalize(sq) === normalize(q.query));
                                return (
                                    <button
                                        key={q.query}
                                        type="button"
                                        className={`choice__btn chip ${isSelected ? "selected" : ""}`}
                                        onClick={() => onToggleQuery(q.query, !isSelected)}
                                    >
                                        {q.query} <span className="percent">{q.relevance}%</span>
                                    </button>
                                );
                            })}
                        </div>

                        <div className="add-custom">
                            <div className="enter__container">
                                <div className="input">
                                    <input
                                        ref={inputRef}
                                        type="text"
                                        placeholder={`Add up to ${MAX_EXTRA} queries (${MAX_EXTRA - extraQueries.length} left)`}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter") {
                                                e.preventDefault();
                                                handleAddExtra();
                                            }
                                        }}
                                        disabled={extraFull}
                                    />
                                    <button type="button" onClick={handleAddExtra} disabled={extraFull}>
                                        <img src="/images/send.png" alt="Send" />
                                    </button>
                                </div>
                            </div>

                            <div className="custom-list">
                                {extraQueries.map((t) => (
                                    <span key={t} className="chip selected">
                                        {t}
                                    </span>
                                ))}
                            </div>
                        </div>
                    </>
                )}

                <button className="submit__btn" onClick={handleGetResults} disabled={selectedCount === 0 || loading}>
                    {loading ? (
                        <>
                            <span className="spinner" /> Getting results...
                        </>
                    ) : (
                        "Get results"
                    )}
                </button>
            </div>
        </div>
    );
}
