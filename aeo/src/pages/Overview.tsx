import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import ReportForm from "../components/forms/ReportForm";
import VisibilityChart from "../components/charts/VisibilityChart";
import AveragePositionChart from "../components/charts/AveragePositionChart";
import type { OverviewData } from "../components/chat/types";
import { fetchOverview, sendReportRequest } from "../lib/api";
import { readJson } from "../lib/auth";

type Cached = { data: OverviewData; ts: number };

const hostOf = (url: string): string => {
    try {
        return new URL(url).host;
    } catch {
        return url;
    }
};

const signed = (n: number, digits: number) => `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;

function Card({ title, loading, children }: { title: string; loading: boolean; children: React.ReactNode }) {
    return (
        <div className={`content ${loading ? "skeleton" : ""}`}>
            <div className="desc">{title}</div>
            {children}
        </div>
    );
}

function ReportModal({
    email,
    name,
    submitting,
    error,
    onEmailChange,
    onNameChange,
    onSubmit,
    onClose,
}: {
    email: string;
    name: string;
    submitting: boolean;
    error: string | null;
    onEmailChange: (v: string) => void;
    onNameChange: (v: string) => void;
    onSubmit: (e: React.FormEvent) => void;
    onClose: () => void;
}) {
    return (
        <div className="modal__overlay" onClick={onClose}>
            <div className="content" onClick={(e) => e.stopPropagation()}>
                <button className="modal__close" onClick={onClose} aria-label="Close">
                    <img src="/images/close.png" alt="" />
                </button>

                <h2>Get the Report and recommendations by email!</h2>
                <div className="login__container">
                    <div className="left">
                        <nav>
                            <ul>
                                <li><img src="/images/check.png" alt="" /> Download PDF report </li>
                                <li><img src="/images/check.png" alt="" /> Get visibility recommendations</li>
                                <li><img src="/images/check.png" alt="" /> Practical tips on content</li>
                            </ul>
                        </nav>
                    </div>
                    <div className="right">
                        <ReportForm
                            email={email}
                            name={name}
                            onEmailChange={onEmailChange}
                            onNameChange={onNameChange}
                            onSubmit={onSubmit}
                            submitting={submitting}
                            error={error || undefined}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}

export default function Overview() {
    const [project] = useState(() => ({
        company_name: localStorage.getItem("company_name") || "",
        website: localStorage.getItem("website") || "",
        geo: localStorage.getItem("geo") || "us",
        selected_queries: readJson<string[]>("selected_queries", []),
        added_queries: readJson<string[]>("added_queries", []),
    }));
    const { company_name, website, geo, selected_queries, added_queries } = project;
    const hasQueries = selected_queries.length + added_queries.length > 0;

    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<OverviewData | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdated, setLastUpdated] = useState<number | null>(null);

    const [reportOpen, setReportOpen] = useState(false);
    const [reportEmail, setReportEmail] = useState("");
    const [reportName, setReportName] = useState("");
    const [reportSubmitting, setReportSubmitting] = useState(false);
    const [reportError, setReportError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);

    const cacheKey = useMemo(
        () => `overview_cache:${company_name}|${website}|${geo}|${[...selected_queries, ...added_queries].join("|")}`,
        [company_name, website, geo, selected_queries, added_queries]
    );

    const domain = useMemo(() => {
        try {
            return new URL(/^https?:\/\//i.test(website) ? website : `https://${website}`).host;
        } catch {
            return website;
        }
    }, [website]);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await fetchOverview({ company_name, website, geo, selected_queries, added_queries });
            const ts = Date.now();
            setData(result);
            setLastUpdated(ts);
            try {
                localStorage.setItem(cacheKey, JSON.stringify({ data: result, ts } satisfies Cached));
            } catch {
                setNotice(null);
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : "Network error");
        } finally {
            setLoading(false);
        }
    }, [company_name, website, geo, selected_queries, added_queries, cacheKey]);

    const initialized = useRef<string | null>(null);
    useEffect(() => {
        if (!hasQueries || initialized.current === cacheKey) return;
        initialized.current = cacheKey;

        const cached = readJson<Cached | null>(cacheKey, null);
        if (cached?.data) {
            setData(cached.data);
            setLastUpdated(cached.ts || null);
        } else {
            void load();
        }
    }, [cacheKey, hasQueries, load]);

    useEffect(() => {
        if (!reportOpen) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") setReportOpen(false);
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [reportOpen]);

    const openReportModal = () => {
        setReportError(null);
        setReportSubmitting(false);
        setReportOpen(true);
    };

    const handleReportSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!reportEmail) return;

        setReportSubmitting(true);
        setReportError(null);
        try {
            await sendReportRequest({
                email: reportEmail,
                name: reportName || undefined,
                domain,
                geo,
                selected_queries: [...selected_queries, ...added_queries],
            });
            setReportOpen(false);
            setReportEmail("");
            setReportName("");
            setNotice("Thanks! We'll email the report and recommendations.");
        } catch (err) {
            setReportError(err instanceof Error ? err.message : "Failed to send request. Try again.");
        } finally {
            setReportSubmitting(false);
        }
    };

    if (!hasQueries) {
        return (
            <div className="Overview panel__container">
                <h2 className="title">Overview</h2>
                <div className="info__container">
                    <p>You haven’t selected any queries yet.</p>
                    <Link className="submit__btn" to="/start">Start analysis</Link>
                </div>
            </div>
        );
    }

    return (
        <div className="Overview panel__container">
            <h2 className="title">Overview</h2>

            <div className="info__container">
                <div className={`date ${loading ? "skeleton-line" : ""}`}>
                    {data ? (
                        <>
                            {new Date(data.period_from).toLocaleString(undefined, { month: "short", day: "numeric" })}
                            {" → "}
                            Today
                            {lastUpdated && (
                                <span style={{ marginLeft: 8, opacity: 0.7 }}>
                                    (updated {new Date(lastUpdated).toLocaleString()})
                                </span>
                            )}
                        </>
                    ) : (
                        <>&nbsp;</>
                    )}
                </div>
                <h3>{domain || company_name}</h3>
                <div className="other">
                    <div>
                        {data ? (
                            <><strong>{data.potential_queries_count}</strong> potential AI comment queries</>
                        ) : (
                            <span className="skeleton-line" style={{ width: 220 }} />
                        )}
                    </div>
                    <div>
                        {data ? (
                            <><strong>{data.weeks_to_top}</strong> weeks to get to the top of AI answers</>
                        ) : (
                            <span className="skeleton-line" style={{ width: 260 }} />
                        )}
                    </div>
                </div>
            </div>

            {error && (
                <p className="form__error" role="alert">
                    {error}
                </p>
            )}
            {notice && <p role="status">{notice}</p>}

            <div className="mainInfo__container">
                <Card title="GENERAL BRAND AI VISIBILITY" loading={loading}>
                    {data ? (
                        <div className="stats big">
                            <div className="kpi">
                                {data.visibility_value.toFixed(1)}%{" "}
                                <span className={data.visibility_delta >= 0 ? "pos vis" : "neg vis"}>
                                    {signed(data.visibility_delta, 1)}%
                                </span>
                            </div>
                            <VisibilityChart data={data.visibility_series} />
                        </div>
                    ) : (
                        <div className="stats big">
                            <div className="kpi skeleton-line" style={{ width: 160 }} />
                            <div className="sparklines skeleton-block" />
                        </div>
                    )}
                </Card>

                <Card title="AI QUERIES" loading={loading}>
                    {data ? (
                        <div className="stats list">
                            {data.ai_queries.map((q) => (
                                <div className="row" key={q.query}>
                                    <span><img src="/images/check2.png" alt="" /> {q.query}</span>
                                    <span className={q.ai_visibility_score > 0 ? "pos score" : "neg score"}>
                                        AI VISIBILITY SCORE - {q.ai_visibility_score.toFixed(1)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="stats list">
                            {[70, 65, 60].map((w) => (
                                <div className="row" key={w}>
                                    <span className="skeleton-line" style={{ width: `${w}%` }} />
                                    <span className="skeleton-line" style={{ width: 120 }} />
                                </div>
                            ))}
                        </div>
                    )}
                </Card>

                <Card title="THE AVERAGE POSITION IN THE ANSWERS" loading={loading}>
                    {data ? (
                        <div className="stats big">
                            <div className="kpi">
                                {data.avg_position_value ?? "—"}
                                {data.avg_position_value !== null && (
                                    <span className={data.avg_position_delta >= 0 ? "pos vis" : "neg vis"}>
                                        {signed(data.avg_position_delta, 1)}
                                    </span>
                                )}
                            </div>
                            <AveragePositionChart data={data.avg_position_series} />
                        </div>
                    ) : (
                        <div className="stats big">
                            <div className="kpi skeleton-line" style={{ width: 120 }} />
                            <div className="sparklines skeleton-block" />
                        </div>
                    )}
                </Card>

                <Card title="CITATION LIST" loading={loading}>
                    {data ? (
                        <div className="stats list">
                            {data.citations.slice(0, 8).map((c) => (
                                <a className="linkrow" href={c.url} target="_blank" rel="noreferrer" key={c.url}>
                                    {hostOf(c.url)}
                                    <span>→</span>
                                </a>
                            ))}
                            {data.citations.length === 0 && <p>No sources were cited in the answers.</p>}
                        </div>
                    ) : (
                        <div className="stats list">
                            {Array.from({ length: 6 }).map((_, i) => (
                                <div className="row" key={i}>
                                    <span className="skeleton-line" style={{ width: "50%" }} />
                                    <span className="skeleton-line" style={{ width: 30 }} />
                                </div>
                            ))}
                        </div>
                    )}
                </Card>
            </div>

            <button className="linkbtn" onClick={openReportModal}>
                Download report and key visibility recommendations
            </button>

            <div className="footerActions">
                <div className="cta">
                    <button className={loading ? "update__btn dis" : "update__btn"} onClick={() => void load()} disabled={loading}>
                        {loading ? "Updating…" : error ? "Retry" : "Update report"}
                    </button>
                    <NavLink to="/plans" className="submit__btn">
                        Improve visibility for selected queries
                    </NavLink>
                </div>
            </div>

            {reportOpen && (
                <ReportModal
                    email={reportEmail}
                    name={reportName}
                    submitting={reportSubmitting}
                    error={reportError}
                    onEmailChange={setReportEmail}
                    onNameChange={setReportName}
                    onSubmit={handleReportSubmit}
                    onClose={() => setReportOpen(false)}
                />
            )}
        </div>
    );
}
