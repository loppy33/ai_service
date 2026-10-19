export interface ChatScreenProps {
    initialBrand?: string;
    initialWebsite?: string;
    initialGeo?: string;
    initialGptAnswer?: string;
    onDone?: (selectedFromUI: string[], addedFromUI: string[]) => void;
}

export interface PhraseOption {
    id: string;
    text: string;
    selected: boolean;
}

export interface SuggestedQuery {
    query: string;
    relevance: number;
}

export interface AnalyzeSerpResponse {
    main_answer?: string | null;
    citations: Array<{ url: string; title: string; snippet?: string | null }>;
    ordered_display: string[];
    ten_suggested_with_relevance: SuggestedQuery[];
}

export type TimeseriesPoint = { date: string; value: number };

export type OverviewData = {
    period_from: string;
    period_to: string;
    website?: string | null;
    company_name: string;
    geo: string;
    potential_queries_count: number;
    weeks_to_top: number;
    visibility_value: number;
    visibility_delta: number;
    visibility_series: TimeseriesPoint[];
    ai_queries: { query: string; ai_visibility_score: number; position?: number | null }[];
    avg_position_value: number | null;
    avg_position_delta: number;
    avg_position_series: TimeseriesPoint[];
    citations: Array<{ url: string; title: string; snippet?: string | null }>;
    main_answer: string;
};

export type Message = { from: "bot" | "user"; text: string };

export type Step = "question" | "clarify" | "phrases" | "queries10" | "noresults" | "done";
