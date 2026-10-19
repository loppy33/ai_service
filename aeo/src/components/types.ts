export interface LoginFormProps {
    mode: "register" | "login";
    email: string;
    password: string;
    projectName: string;
    subscribe: boolean;
    submitting?: boolean;
    error?: string;
    onEmailChange: (val: string) => void;
    onPasswordChange: (val: string) => void;
    onProjectNameChange: (val: string) => void;
    onSubscribeChange: (val: boolean) => void;
    onToggleMode: () => void;
    onSubmit: (e: React.FormEvent) => void;
}

export interface ReportFormProps {
    email: string;
    name: string;
    onEmailChange: (val: string) => void;
    onNameChange: (val: string) => void;
    onSubmit: (e: React.FormEvent) => void;
    submitting?: boolean;
    error?: string;
}

export interface AnalyzeScreenProps {
    defaultWebsite?: string;
    defaultBrand?: string;
    onAnalyze: (data: { website: string; brand: string; market: string }) => Promise<void> | void;
}
