import type { AnalyzeSerpResponse, OverviewData } from "../components/chat/types";
import { API_URL } from "../config";
import { clearSession, getToken } from "./auth";

export class ApiError extends Error {
    status: number;

    constructor(message: string, status: number) {
        super(message);
        this.status = status;
    }
}

function errorMessage(body: unknown, fallback: string): string {
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: string };
        if (first?.msg) return first.msg;
    }
    return fallback;
}

async function request<T>(path: string, init: RequestInit & { auth?: boolean } = {}): Promise<T> {
    const { auth = true, headers, ...rest } = init;
    const finalHeaders: Record<string, string> = { "Content-Type": "application/json", ...(headers as Record<string, string>) };
    const token = getToken();
    if (auth && token) finalHeaders.Authorization = `Bearer ${token}`;

    let res: Response;
    try {
        res = await fetch(`${API_URL}${path}`, { ...rest, headers: finalHeaders });
    } catch {
        throw new ApiError("Cannot reach the server. Please try again later.", 0);
    }

    const body = await res.json().catch(() => null);
    if (!res.ok) {
        if (res.status === 401 && auth) clearSession();
        throw new ApiError(errorMessage(body, `Request failed (${res.status})`), res.status);
    }
    return body as T;
}

const post = <T>(path: string, data: unknown, auth = true) =>
    request<T>(path, { method: "POST", body: JSON.stringify(data), auth });

export type AuthResult = { token: string; email: string; projectName: string };

export const register = (data: { email: string; password: string; projectName: string; subscribe: boolean }) =>
    post<AuthResult>("/auth/register", data, false);

export const login = (data: { email: string; password: string }) => post<AuthResult>("/auth/login", data, false);

export const fetchMe = () => request<{ email: string; projectName: string; paid: boolean }>("/auth/me");

export const brandInsight = (data: { brand: string; website: string; country: string; language: string }) =>
    post<{ gpt_answer: string; understood: boolean }>("/analyze/brand-insight", data);

export const collectPhrases = (company_name: string, geo?: string) =>
    post<{ phrases?: string[] }>("/analyze/collect-phrases", { company_name, geo: geo || "us" });

export async function suggestQueries(params: {
    seedQueries: string[];
    geo?: string;
    company_name?: string;
    website?: string;
}): Promise<Pick<AnalyzeSerpResponse, "ten_suggested_with_relevance">> {
    const data = await post<AnalyzeSerpResponse>("/analyze/serp", {
        queries: params.seedQueries,
        geo: params.geo || "us",
        company_name: params.company_name || "",
        website: params.website,
    });
    return { ten_suggested_with_relevance: data.ten_suggested_with_relevance };
}

export const fetchOverview = (data: {
    company_name: string;
    website: string;
    geo: string;
    selected_queries: string[];
    added_queries: string[];
}) => post<OverviewData>("/analyze/overview", data);

export const sendReportRequest = (payload: {
    email: string;
    name?: string;
    domain?: string;
    geo?: string;
    selected_queries: string[];
}) => post<{ ok: boolean }>("/leads/report-request", payload);

export const sendContactRequest = (payload: { email: string; contact?: string; name?: string }) =>
    post<{ ok: boolean }>("/leads/contact-request", payload);

export const createCheckoutSession = (package_id: "basic" | "pro", project_id: string) =>
    post<{ url: string }>("/billing/create-checkout-session", { package_id, project_id });
