/**
 * The 12 curated lessons and their comprehension checks.
 *
 * The content is written by people, not generated, so this page renders it
 * verbatim and adds nothing. The answers only arrive once the user has
 * committed to theirs, which is why the topic payload contains neither the
 * right option nor the per-question explanation.
 *
 * All three questions are answered before anything is marked. The
 * alternative, marking each as it is tapped, turns the second and third
 * questions into a different exercise: once you know you got the first one
 * wrong you are being tested on your reaction to that, not on the lesson.
 * It also means one submission, so the score written down is the score the
 * user actually earned in one pass.
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
  /** Chosen option per question index. Sparse until the quiz is finished. */
  const [picked, setPicked] = useState<Record<number, number>>({});

  const topics = useQuery({ queryKey: ["topics"], queryFn: listTopics });

  const topic = useQuery({
    queryKey: ["topic", openKey],
    queryFn: () => getTopic(openKey!),
    enabled: Boolean(openKey),
  });

  const answer = useMutation({
    mutationFn: (answers: number[]) => submitQuiz(openKey!, answers),
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
    setPicked({});
  }

  const questions = topic.data?.questions ?? [];
  const answered = questions.length > 0
    && questions.every((_, index) => picked[index] !== undefined);

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

                <h4>Quick check</h4>
                {result === null ? (
                  <>
                    {topic.data.questions.map((question, qIndex) => (
                      <fieldset key={question.question} className="quiz">
                        <legend>
                          {qIndex + 1}. {question.question}
                        </legend>
                        <ul className="choices">
                          {question.options.map((option, index) => (
                            <li key={option}>
                              <label>
                                <input
                                  type="radio"
                                  name={`q-${openKey}-${qIndex}`}
                                  value={index}
                                  checked={picked[qIndex] === index}
                                  onChange={() =>
                                    setPicked((current) => ({ ...current, [qIndex]: index }))
                                  }
                                />
                                {" "}{option}
                              </label>
                            </li>
                          ))}
                        </ul>
                      </fieldset>
                    ))}
                    <div className="actions">
                      <button
                        type="button"
                        className="primary"
                        disabled={!answered || answer.isPending}
                        onClick={() =>
                          answer.mutate(questions.map((_, index) => picked[index]))
                        }
                      >
                        {answer.isPending ? "Checking…" : "Check my answers"}
                      </button>
                    </div>
                    {!answered && (
                      <p className="muted">
                        Answer all {questions.length} to see how you did. Nothing is
                        marked until then.
                      </p>
                    )}
                  </>
                ) : (
                  <div role="status" className="result">
                    <p>
                      <strong>
                        {result.correct_count} of {result.total} right.
                      </strong>
                    </p>
                    <ol className="quiz-marks">
                      {result.answers.map((mark, index) => (
                        <li key={topic.data!.questions[index].question}>
                          <p>
                            <strong>{mark.correct ? "Correct." : "Not quite."}</strong>{" "}
                            {topic.data!.questions[index].options[mark.correct_idx]}
                          </p>
                          {/* Shown for the right answers too: nobody can tell
                              from the outside whether a correct answer was
                              knowledge or a guess. */}
                          <p className="muted">{mark.why}</p>
                        </li>
                      ))}
                    </ol>
                    <div className="actions">
                      <button type="button" onClick={() => { setResult(null); setPicked({}); }}>
                        Try again
                      </button>
                    </div>
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
