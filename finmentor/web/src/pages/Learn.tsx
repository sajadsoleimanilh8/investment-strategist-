/**
 * The 12 curated lessons and their comprehension checks.
 *
 * The content is written by people, not generated — so this page renders it
 * verbatim and adds nothing. The quiz answer only arrives after the user has
 * committed to one, which is why the topic payload does not contain it.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getTopic, listTopics, submitQuiz } from "../api/learn";
import { AsyncBoundary } from "../components/AsyncBoundary";
import type { QuizResult } from "../api/types";

export function Learn() {
  const queryClient = useQueryClient();
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [result, setResult] = useState<QuizResult | null>(null);

  const topics = useQuery({ queryKey: ["topics"], queryFn: listTopics });

  const topic = useQuery({
    queryKey: ["topic", openKey],
    queryFn: () => getTopic(openKey!),
    enabled: Boolean(openKey),
  });

  const answer = useMutation({
    mutationFn: (answerIdx: number) => submitQuiz(openKey!, answerIdx),
    onSuccess: (data) => {
      setResult(data);
      // Completing a topic raises the knowledge band in Financial DNA, so the
      // dashboard is stale too.
      queryClient.invalidateQueries({ queryKey: ["topics"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
    },
  });

  function open(key: string) {
    setOpenKey(key === openKey ? null : key);
    setResult(null);
  }

  return (
    <>
      <section>
        <h2>Learn</h2>
        <AsyncBoundary isLoading={topics.isLoading} error={topics.error}>
          <p className="muted">
            {topics.data?.completed_count ?? 0} of {topics.data?.items.length ?? 0} done.
          </p>
          <ul className="rows">
            {topics.data?.items.map((item) => (
              <li key={item.key}>
                {/* The whole title is the control, and the state sits at the
                    other end of the row. One word, not a tick and a separator:
                    a glyph has to be decoded, and "passed" does not. */}
                <button
                  type="button"
                  className="row-button"
                  aria-expanded={openKey === item.key}
                  onClick={() => open(item.key)}
                >
                  <span>{item.title}</span>
                  <span className="rows__state">
                    {item.quiz_score === 100 ? "passed" : item.completed ? "read" : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </AsyncBoundary>
      </section>

      {openKey && (
        <section>
          <AsyncBoundary isLoading={topic.isLoading} error={topic.error}>
            {topic.data && (
              <article className="result">
                <h3>{topic.data.title}</h3>
                <p>{topic.data.explanation}</p>

                <h4>For example</h4>
                <p>{topic.data.example}</p>

                <h4>The mistake to avoid</h4>
                <p>{topic.data.common_mistake}</p>

                <h4>{topic.data.quiz.question}</h4>
                {result === null ? (
                  <ul className="choices">
                    {topic.data.quiz.options.map((option, index) => (
                      <li key={option}>
                        <button
                          type="button"
                          onClick={() => answer.mutate(index)}
                          disabled={answer.isPending}
                        >
                          {option}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div role="status" className="result">
                    <p>
                      <strong>{result.correct ? "Correct." : "Not quite."}</strong>{" "}
                      The answer is: {topic.data.quiz.options[result.correct_idx]}
                    </p>
                    <p>{result.explanation}</p>
                  </div>
                )}
              </article>
            )}
          </AsyncBoundary>
        </section>
      )}
    </>
  );
}
