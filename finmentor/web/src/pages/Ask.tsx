/**
 * The conversational surface.
 *
 * Two things are deliberately visible to the user that a chat UI usually
 * hides: which tier answered (`source`) and the disclaimer. When the model is
 * down, `deterministic` means the reply is the verified figures rendered
 * plainly — that is a different kind of answer and the user is entitled to
 * know which one they got.
 */
import { type FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ask as askApi, transcript as transcriptApi } from "../api/ask";
import { AsyncBoundary } from "../components/AsyncBoundary";
import { FormError } from "../components/FormError";
import { useAuth } from "../auth/AuthContext";
import type { AskResponse } from "../api/types";

const SOURCE_LABELS: Record<string, string> = {
  local: "answered by the local model",
  hybrid: "answered by two models, merged",
  deterministic: "the model was unavailable — these are your verified figures",
};

const SUGGESTIONS = [
  "why is my health score what it is?",
  "how am I doing?",
  "what if I save 2m more each month?",
  "what should I focus on first?",
  "what does diversification mean?",
];

export function Ask() {
  const { user } = useAuth();
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<{ question: string; response: AskResponse }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const history = useQuery({
    queryKey: ["transcript", user?.id],
    queryFn: () => transcriptApi(user!.id),
    enabled: Boolean(user),
  });

  const send = useMutation({
    mutationFn: (text: string) => askApi(user!.id, text),
    onSuccess: (response, text) => {
      setAnswers((all) => [...all, { question: text, response }]);
      setQuestion("");
    },
    onError: (caught) =>
      setError(caught instanceof Error ? caught.message : "Could not answer that."),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const text = question.trim();
    if (!text) return;
    send.mutate(text);
  }

  return (
    <>
      <section>
        <h2>Ask me about your money</h2>
        <form onSubmit={submit}>
          <p className="field">
            <label htmlFor="question">Your question</label>
            <textarea
              id="question"
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="why is my score what it is?"
            />
          </p>
          <div className="actions">
            <button type="submit" disabled={send.isPending || !question.trim()}>
              {send.isPending ? "Thinking…" : "Ask"}
            </button>
          </div>
        </form>
        <FormError message={error} />

        <details>
          <summary>Things you can ask</summary>
          <ul>
            {SUGGESTIONS.map((suggestion) => (
              <li key={suggestion}>
                <button type="button" onClick={() => setQuestion(suggestion)}>
                  {suggestion}
                </button>
              </li>
            ))}
          </ul>
        </details>
      </section>

      {answers.length > 0 && (
        <section>
          <h2>This session</h2>
          {answers.map((entry, index) => (
            <article key={index}>
              <h3>{entry.question}</h3>
              {/* The reply is plain text with newlines, not markup. */}
              <p style={{ whiteSpace: "pre-wrap" }}>{entry.response.text}</p>
              <p className="disclaimer">
                <small>
                  {SOURCE_LABELS[entry.response.source] ?? entry.response.source}
                </small>
              </p>
            </article>
          ))}
        </section>
      )}

      <section>
        <h2>Earlier</h2>
        <AsyncBoundary
          isLoading={history.isLoading}
          error={history.error}
          isEmpty={history.data?.length === 0}
          emptyMessage="Nothing yet."
        >
          <ul>
            {history.data?.slice(-10).reverse().map((turn, index) => (
              <li key={index}>
                <strong>{turn.question}</strong>
                <br />
                {turn.answer}
              </li>
            ))}
          </ul>
        </AsyncBoundary>
      </section>
    </>
  );
}
