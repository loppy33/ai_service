import { useState } from "react";

export function QuestionStep({ onAnswer }: { onAnswer: (ok: boolean) => void }) {
    const [hidden, setHidden] = useState(false);

    const handleClick = (ok: boolean) => {
        setHidden(true);
        onAnswer(ok);
    };

    if (hidden) return null;

    return (
        <div className="response user choices">
            <button className="choice__btn" onClick={() => handleClick(true)}>
                Yes, you got it right
            </button>
            <button className="choice__btn" onClick={() => handleClick(false)}>
                No, that’s not my brand
            </button>
        </div>
    );
}
