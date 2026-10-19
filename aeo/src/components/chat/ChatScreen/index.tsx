import { useMemo, useState } from "react";
import type { ChatScreenProps, Message, PhraseOption, Step, SuggestedQuery } from "../types";
import { MessageList } from "../MessageList";
import { QuestionStep } from "../steps/QuestionStep";
import { ClarifyStep } from "../steps/ClarifyStep";
import { PhrasesStep } from "../steps/PhrasesStep";
import { QueriesStep } from "../steps/QueriesStep";
import { NoResultsStep } from "../steps/NoResultsStep";
import { collectPhrases, sendReportRequest, suggestQueries } from "../../../lib/api";

const FALLBACK_DESCRIPTION = "I don't have enough public info yet";
const MAX_CUSTOM_PHRASES = 5;
const MAX_EXTRA_QUERIES = 5;

const toOptions = (phrases: string[] = []): PhraseOption[] =>
    phrases.map((text, i) => ({ id: String(i), text, selected: false }));

export default function ChatScreen({ initialBrand, initialWebsite, initialGeo, initialGptAnswer, onDone }: ChatScreenProps) {
    const description = (initialGptAnswer || "").trim().replace(/[.\s]+$/, "") || FALLBACK_DESCRIPTION;

    const [messages, setMessages] = useState<Message[]>(() => [
        { from: "bot", text: `If I understand correctly, your company is ${description}. Is this true?` },
    ]);
    const [step, setStep] = useState<Step>("question");
    const [userInput, setUserInput] = useState("");
    const [phraseOptions, setPhraseOptions] = useState<PhraseOption[]>([]);
    const [customPhrases, setCustomPhrases] = useState<string[]>([]);
    const [serpSuggestions, setSerpSuggestions] = useState<SuggestedQuery[]>([]);
    const [selectedQueries, setSelectedQueries] = useState<string[]>([]);
    const [extraQueries, setExtraQueries] = useState<string[]>([]);
    const [leadEmail, setLeadEmail] = useState("");
    const [leadName, setLeadName] = useState("");
    const [leadSubmitting, setLeadSubmitting] = useState(false);

    const say = (...next: Message[]) => setMessages((prev) => [...prev, ...next]);

    const loadPhrases = async (companyName: string, intro: string) => {
        try {
            const data = await collectPhrases(companyName, initialGeo);
            setPhraseOptions(toOptions(data.phrases));
            say({ from: "bot", text: intro });
        } catch {
            setPhraseOptions([]);
            say({ from: "bot", text: "I couldn't load suggestions right now. You can add your own phrases below." });
        }
        setStep("phrases");
    };

    const togglePhrase = (id: string) => {
        setPhraseOptions((prev) => prev.map((p) => (p.id === id ? { ...p, selected: !p.selected } : p)));
    };

    const handleAnswer = (isCorrect: boolean) => {
        if (isCorrect) {
            say({ from: "user", text: "Yes, you got it right" });
            void loadPhrases(
                initialBrand || description,
                "Here are some phrases related to your business with commercial intent. Please select the relevant ones or add yours."
            );
        } else {
            say({ from: "user", text: "No, that’s not my brand" }, { from: "bot", text: "Can you tell me a bit about your company?" });
            setStep("clarify");
        }
    };

    const handleClarifySend = () => {
        const text = userInput.trim();
        if (!text) return;
        say({ from: "user", text });
        setUserInput("");
        void loadPhrases(text, "Thanks! Select or add phrases relevant to you.");
    };

    const selectedPhrasesTexts = useMemo(
        () => phraseOptions.filter((p) => p.selected).map((p) => p.text).concat(customPhrases),
        [phraseOptions, customPhrases]
    );

    const handleGenerate10 = async () => {
        if (selectedPhrasesTexts.length === 0) return;
        say({ from: "user", text: `Generate queries for:\n- ${selectedPhrasesTexts.join("\n- ")}` });

        try {
            const { ten_suggested_with_relevance } = await suggestQueries({
                seedQueries: selectedPhrasesTexts,
                geo: initialGeo,
                company_name: initialBrand,
                website: initialWebsite,
            });
            setSerpSuggestions(ten_suggested_with_relevance);
            say({ from: "bot", text: "Here are the relevant queries with relevance %. Choose the ones that matter, or add up to 5." });
            setStep("queries10");
        } catch {
            setSerpSuggestions([]);
            say({
                from: "bot",
                text: "I couldn’t generate the queries right now. Leave your email and we’ll send you the report with recommendations.",
            });
            setStep("noresults");
        }
    };

    const handleGetResults = () => {
        onDone?.(selectedQueries, extraQueries);
    };

    const handleLeadSubmit = async () => {
        if (!leadEmail || leadSubmitting) return;
        setLeadSubmitting(true);
        try {
            await sendReportRequest({
                email: leadEmail,
                name: leadName || undefined,
                domain: initialWebsite,
                geo: initialGeo,
                selected_queries: selectedPhrasesTexts,
            });
            say({ from: "bot", text: "Thanks! We’ve emailed the report and recommendations." });
            setStep("done");
        } catch (err) {
            say({ from: "bot", text: err instanceof Error ? `Sorry, ${err.message}` : "Sorry, something went wrong. Please try again." });
        } finally {
            setLeadSubmitting(false);
        }
    };

    return (
        <div className="chat__container">
            <MessageList messages={messages} />

            {step === "question" && <QuestionStep onAnswer={handleAnswer} />}

            {step === "clarify" && <ClarifyStep value={userInput} onChange={setUserInput} onSend={handleClarifySend} />}

            {step === "phrases" && (
                <PhrasesStep
                    phraseOptions={phraseOptions}
                    customPhrases={customPhrases}
                    onToggle={togglePhrase}
                    onAddCustom={(v) => {
                        if (customPhrases.length < MAX_CUSTOM_PHRASES) setCustomPhrases((prev) => [...prev, v]);
                    }}
                    onGenerate={handleGenerate10}
                />
            )}

            {step === "queries10" && serpSuggestions.length > 0 && (
                <QueriesStep
                    suggestions={serpSuggestions}
                    selectedQueries={selectedQueries}
                    onToggleQuery={(q, checked) =>
                        setSelectedQueries((prev) => (checked ? [...prev, q] : prev.filter((x) => x !== q)))
                    }
                    extraQueries={extraQueries}
                    onAddExtraQuery={(q) => {
                        if (extraQueries.length < MAX_EXTRA_QUERIES) setExtraQueries((prev) => [...prev, q]);
                    }}
                    onGetResults={handleGetResults}
                />
            )}

            {step === "noresults" && (
                <NoResultsStep
                    email={leadEmail}
                    name={leadName}
                    submitting={leadSubmitting}
                    onChangeEmail={setLeadEmail}
                    onChangeName={setLeadName}
                    onSubmit={handleLeadSubmit}
                />
            )}
        </div>
    );
}
