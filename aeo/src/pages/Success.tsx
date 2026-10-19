import { Link, useSearchParams } from "react-router-dom";

export default function Success() {
    const [params] = useSearchParams();
    const cancelled = params.get("cancelled") === "1";

    return (
        <div className="Home">
            <div className="Home__card">
                <div className="Home__logo">👁️ SeeUinAI</div>
                <h1>{cancelled ? "Payment cancelled" : "Thank you for your payment!"}</h1>
                <p>
                    {cancelled
                        ? "No charges were made. You can choose a plan again at any time."
                        : "Your payment was received. We will contact you shortly to start the promotion."}
                </p>
                <Link className="submit__btn Home__cta" to={cancelled ? "/plans" : "/overview"}>
                    {cancelled ? "Back to plans" : "Back to dashboard"}
                </Link>
            </div>
        </div>
    );
}
