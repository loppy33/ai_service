import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { AnalyzeScreen } from "../components/AnalyzeScreen";
import ChatScreen from "../components/chat/ChatScreen";
import { brandInsight } from "../lib/api";
import { clearProject, getToken } from "../lib/auth";

type Analyzed = { website: string; brand: string; market: string };

export default function Onboarding() {
    const navigate = useNavigate();
    const [analyzed, setAnalyzed] = useState<Analyzed | null>(null);
    const [gptAnswer, setGptAnswer] = useState("");

    if (!getToken()) {
        return <Navigate to="/login" replace />;
    }

    const handleAnalyze = async (payload: Analyzed) => {
        clearProject();
        localStorage.setItem("company_name", payload.brand);
        localStorage.setItem("website", payload.website);
        localStorage.setItem("geo", payload.market);

        try {
            const data = await brandInsight({
                brand: payload.brand,
                website: payload.website,
                country: payload.market,
                language: "en",
            });
            setGptAnswer(data.understood ? data.gpt_answer : "");
        } catch {
            setGptAnswer("");
        }
        setAnalyzed(payload);
    };

    const handleDone = (selected: string[], added: string[]) => {
        localStorage.setItem("selected_queries", JSON.stringify(selected));
        localStorage.setItem("added_queries", JSON.stringify(added));
        navigate("/overview");
    };

    if (analyzed) {
        return (
            <div className="Login">
                <ChatScreen
                    initialBrand={analyzed.brand}
                    initialWebsite={analyzed.website}
                    initialGeo={analyzed.market}
                    initialGptAnswer={gptAnswer}
                    onDone={handleDone}
                />
            </div>
        );
    }

    return (
        <div className="Login">
            <div className="analyze__container">
                <AnalyzeScreen onAnalyze={handleAnalyze} />
            </div>
        </div>
    );
}
