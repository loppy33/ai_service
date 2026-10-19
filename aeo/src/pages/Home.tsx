import { Link } from "react-router-dom";
import { getToken } from "../lib/auth";

export default function Home() {
    const loggedIn = !!getToken();

    return (
        <div className="Home container">
            <h1>AI visibility for your brand</h1>
            <p>Find out how often AI assistants mention your brand and what to do about it.</p>
            {loggedIn ? <Link to="/overview">Open dashboard</Link> : <Link to="/login">Login</Link>}
        </div>
    );
}
