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
          <p>
            {topics.data?.completed_count ?? 0} of {topics.data?.items.length ?? 0} done.
          </p>
          <ul>
            {topics.data?.items.map((item) => (
              <li key={item.key}>
                <button type="button" onClick={() => open(item.key)}>
                  {item.title}
                </button>
                {item.completed && <span> ✓ read</span>}
                {item.quiz_score === 100 && <span> · got it right</span>}
              </li>
            ))}
          </ul>
        </AsyncBoundary>
      </section>

      {openKey && (
        <section>
          <AsyncBoundary isLoading={topic.isLoading} error={topic.error}>
            {topic.data && (
              <article>
                <h3>{topic.data.title}</h3>
                <p>{topic.data.explanation}</p>

                <h4>For example</h4>
                <p>{topic.data.example}</p>

                <h4>The mistake to avoid</h4>
                <p>{topic.data.common_mistake}</p>

                <h4>{topic.data.quiz.question}</h4>
                {result === null ? (
                  <ul>
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
                  <div role="status">
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
