import { useState } from "react";
import type { AnalyzeScreenProps } from "./types";

const WEBSITE_RE = /^(https?:\/\/)?([a-z0-9-]+\.)+[a-z]{2,}(\/\S*)?$/i;

export function AnalyzeScreen({ defaultWebsite = "", defaultBrand = "", onAnalyze }: AnalyzeScreenProps) {
    const [website, setWebsite] = useState(defaultWebsite);
    const [brand, setBrand] = useState(defaultBrand);
    const [market, setMarket] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleAnalyze = async (e: React.FormEvent) => {
        e.preventDefault();
        const site = website.trim();
        if (!site || !brand.trim() || !market) {
            setError("Please complete all fields before analyzing.");
            return;
        }
        if (!WEBSITE_RE.test(site)) {
            setError("Please enter a valid website, e.g. www.website.com");
            return;
        }

        setError(null);
        setLoading(true);
        try {
            await onAnalyze({ website: site, brand: brand.trim(), market });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>
            <div className="title">
                <h2>Hi, I’m SeeUinAI Bot</h2>
                <p>Tell me about your Brand</p>
            </div>
            <form onSubmit={handleAnalyze}>
                <div>
                    <input
                        className="input border"
                        type="text"
                        placeholder="www.website.com"
                        value={website}
                        onChange={(e) => setWebsite(e.target.value)}
                        required
                    />
                </div>
                <div>
                    <input
                        className="input border"
                        type="text"
                        placeholder="Brand name..."
                        value={brand}
                        onChange={(e) => setBrand(e.target.value)}
                        required
                    />
                </div>
                <div>
                    <select
                        className="input border"
                        value={market}
                        onChange={(e) => setMarket(e.target.value)}
                        required
                    >
                        <option value="">Select Target Market</option>
                        <option value="us">United States</option>
                        <option value="eu">European Union</option>
                        <option value="uk">United Kingdom</option>
                        <option value="ca">Canada</option>
                        <option value="au">Australia</option>
                    </select>
                </div>
                {error && <p className="form__error">{error}</p>}
                <div>
                    <button className="submit__btn" type="submit" disabled={loading}>
                        {loading ? (
                            <>
                                <span className="spinner" /> Analyzing...
                            </>
                        ) : (
                            "Analyze"
                        )}
                    </button>
                </div>
            </form>
        </div>
    );
}
