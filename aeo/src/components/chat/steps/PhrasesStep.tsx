import { useState } from "react";
import type { PhraseOption } from "../types";

const MAX_PHRASES = 10;

export function PhrasesStep({
    phraseOptions,
    customPhrases,
    onToggle,
    onAddCustom,
    onGenerate,
}: {
    phraseOptions: PhraseOption[];
    customPhrases: string[];
    onToggle: (id: string) => void;
    onAddCustom: (v: string) => void;
    onGenerate: () => Promise<void> | void;
}) {
    const [loading, setLoading] = useState(false);
    const [inputValue, setInputValue] = useState("");

    const selectedCount = phraseOptions.filter((p) => p.selected).length + customPhrases.length;
    const maxReached = selectedCount >= MAX_PHRASES;

    const handleAdd = () => {
        const v = inputValue.trim();
        if (!v) return;
        if (maxReached) {
            alert(`You can select up to ${MAX_PHRASES} phrases total.`);
            return;
        }
        if (customPhrases.some((p) => p.toLowerCase() === v.toLowerCase())) {
            setInputValue("");
            return;
        }
        onAddCustom(v);
        setInputValue("");
    };

    const handleGenerateClick = async () => {
        if (selectedCount === 0 || loading) return;
        setLoading(true);
        try {
            await onGenerate();
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
                            {phraseOptions.length === 0 && (
                                <p className="content" style={{ opacity: 0.6 }}>
                                    [ No suggestions. Add your own phrases below ]
                                </p>
                            )}

                            {phraseOptions.map((p) => (
                                <button
                                    key={p.id}
                                    type="button"
                                    className={`choice__btn chip ${p.selected ? "selected" : ""}`}
                                    onClick={() => {
                                        if (maxReached && !p.selected) {
                                            alert(`You can select up to ${MAX_PHRASES} phrases total.`);
                                            return;
                                        }
                                        onToggle(p.id);
                                    }}
                                >
                                    {p.text}
                                </button>
                            ))}
                        </div>

                        <div className="add-custom">
                            <div className="enter__container">
                                <div className="input">
                                    <input
                                        type="text"
                                        placeholder={`Add your phrase (${MAX_PHRASES - selectedCount} left)`}
                                        value={inputValue}
                                        disabled={maxReached}
                                        onChange={(e) => setInputValue(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter") {
                                                e.preventDefault();
                                                handleAdd();
                                            }
                                        }}
                                    />
                                    <button type="button" onClick={handleAdd} disabled={maxReached}>
                                        <img src="/images/send.png" alt="Send" />
                                    </button>
                                </div>
                            </div>

                            <div className="custom-list">
                                {customPhrases.map((t) => (
                                    <span key={t} className="chip selected">
                                        {t}
                                    </span>
                                ))}
                            </div>
                        </div>

                        <div style={{ opacity: 0.7, fontSize: "0.9em" }}>
                            Selected: {selectedCount}/{MAX_PHRASES}
                        </div>
                    </>
                )}

                <button className="submit__btn" onClick={handleGenerateClick} disabled={selectedCount === 0 || loading}>
                    {loading ? (
                        <>
                            <span className="spinner" /> Generating...
                        </>
                    ) : (
                        "Generate relevant queries"
                    )}
                </button>
            </div>
        </div>
    );
}
