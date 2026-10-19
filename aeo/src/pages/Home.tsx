import { Link } from "react-router-dom";
import { getToken } from "../lib/auth";

export default function Home() {
    const loggedIn = !!getToken();

    return (
        <div className="Home">
            <div className="Home__card">
                <div className="Home__logo">👁️ SeeUinAI</div>
                <h1>AI visibility for your brand</h1>
                <p>Find out how often AI assistants mention your brand and what to do about it.</p>
                <Link className="submit__btn Home__cta" to={loggedIn ? "/overview" : "/login"}>
                    {loggedIn ? "Open dashboard" : "Login"}
                </Link>
            </div>
        </div>
    );
}
