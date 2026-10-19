const TOKEN_KEY = "auth_token";

export const PROJECT_KEYS = ["company_name", "website", "geo", "selected_queries", "added_queries"] as const;

export function getToken(): string | null {
    try {
        return localStorage.getItem(TOKEN_KEY);
    } catch {
        return null;
    }
}

export function setToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
}

export function clearSession(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem("projectName");
}

export function clearProject(): void {
    PROJECT_KEYS.forEach((k) => localStorage.removeItem(k));
}

export function readJson<T>(key: string, fallback: T): T {
    try {
        const raw = localStorage.getItem(key);
        return raw ? (JSON.parse(raw) as T) : fallback;
    } catch {
        return fallback;
    }
}
