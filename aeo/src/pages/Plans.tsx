import { useState } from "react";
import ContactForm from "../components/forms/ContactForm";
import { createCheckoutSession } from "../lib/api";

type Plan = {
    id: "basic" | "pro" | "custom";
    name: string;
    priceLabel: string;
    features: string[];
    cta: string;
};

const plans: Plan[] = [
    {
        id: "basic",
        name: "Basic",
        priceLabel: "$1500",
        features: ["3 queries optimization", "One project", "AI monitoring queries", "Monthly reports"],
        cta: "Go to payment",
    },
    {
        id: "pro",
        name: "Pro",
        priceLabel: "$4200",
        features: [
            "10 queries optimization",
            "Three project",
            "AI monitoring queries",
            "Monthly reports",
            "Content suggestions on email",
            "Link optimization",
        ],
        cta: "Go to payment",
    },
    {
        id: "custom",
        name: "Custom",
        priceLabel: "$ under your budget",
        features: ["Any number of queries", "Updates from your personal manager", "SEO + AEO"],
        cta: "Leave a request",
    },
];

function ContactModal({ onClose, onSent }: { onClose: () => void; onSent: () => void }) {
    return (
        <div className="modal__overlay" onClick={onClose}>
            <div className="content" onClick={(e) => e.stopPropagation()}>
                <button className="modal__close" onClick={onClose} aria-label="Close">
                    <img src="/images/close.png" alt="" />
                </button>

                <h2>Get Your Custom Promotion Plan</h2>
                <div className="login__container">
                    <div className="left">
                        <nav>
                            <ul>
                                <li><img src="/images/check.png" alt="" /> Unlimited number of prompts </li>
                                <li><img src="/images/check.png" alt="" /> Automated + manual promotion</li>
                                <li><img src="/images/check.png" alt="" /> Personal action plan</li>
                            </ul>
                        </nav>
                    </div>
                    <div className="right">
                        <ContactForm onSent={onSent} />
                    </div>
                </div>
            </div>
        </div>
    );
}

export default function Plans() {
    const [contactOpen, setContactOpen] = useState(false);
    const [activeId, setActiveId] = useState<Plan["id"] | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    const projectId = localStorage.getItem("projectName") || "project";

    const resetSelection = () => {
        setContactOpen(false);
        setActiveId(null);
    };

    const goCheckout = async (pkg: "basic" | "pro") => {
        setMessage(null);
        try {
            const { url } = await createCheckoutSession(pkg, projectId);
            window.location.href = url;
        } catch (err) {
            setActiveId(null);
            setMessage(err instanceof Error ? err.message : "Payment init failed. Try again later.");
        }
    };

    const handleClick = (p: Plan) => {
        setActiveId(p.id);
        if (p.id === "custom") {
            setContactOpen(true);
        } else {
            void goCheckout(p.id);
        }
    };

    return (
        <div className="Plans panel__container">
            <h2 className="title">Tariff plans</h2>

            <section>
                <h3 className="sec__title">
                    Choose the right plan to meet your SEO <br /> needs and start optimizing today.
                </h3>
                {message && (
                    <p className="form__error" role="alert">
                        {message}
                    </p>
                )}
                <div className="articles">
                    {plans.map((p) => {
                        const isDisabled = activeId !== null && p.id !== activeId;
                        return (
                            <article id={p.id} key={p.id}>
                                <div>
                                    <h3>{p.name}</h3>
                                    <p>{p.priceLabel}</p>
                                    <ul>
                                        {p.features.map((f) => (
                                            <li key={f}>
                                                <img
                                                    src={p.id === "pro" ? "/images/checkBlack.png" : "/images/checkWhite.png"}
                                                    alt=""
                                                />{" "}
                                                {f}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                                <button
                                    className={`article__btn ${isDisabled ? "is-disabled" : ""}`}
                                    onClick={() => handleClick(p)}
                                    disabled={isDisabled}
                                    aria-disabled={isDisabled}
                                >
                                    {p.cta}
                                </button>
                            </article>
                        );
                    })}
                </div>
            </section>

            {contactOpen && (
                <ContactModal
                    onClose={resetSelection}
                    onSent={() => {
                        resetSelection();
                        setMessage("Thanks! We’ll contact you shortly.");
                    }}
                />
            )}
        </div>
    );
}
