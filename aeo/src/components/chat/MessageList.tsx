import ReactMarkdown from "react-markdown";
import type { Message } from "./types";
import remarkGfm from "remark-gfm";
import { useEffect, useRef } from "react";

export function MessageList({ messages }: { messages: Message[] }) {
    const endRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }, [messages]);

    return (
        <div className="messages__container">
            {messages.map((m, i) => (
                <div key={i} className={`message ${m.from}`}>
                    {m.from === "bot" ? <span>SeeUinAI</span> : <span>You</span>}
                    <div className="content markdown">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {m.text}
                        </ReactMarkdown>
                    </div>
                </div>
            ))}
            <div ref={endRef} />
        </div>
    );
}