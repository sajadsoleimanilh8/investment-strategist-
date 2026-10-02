/**
 * The lesson page, and mostly the quiz.
 *
 * The decision worth testing is that nothing is marked until all three
 * questions are answered. Marking each tap would make questions two and three
 * a different exercise: once you know you got the first one wrong, you are
 * being tested on your reaction to that rather than on the lesson. It also
 * keeps the attempt to one submission, so the score recorded is the score
 * earned in one pass.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Learn } from "./Learn";
import type { QuizResult, Topic, TopicListOut } from "../api/types";

const LISTING: TopicListOut = {
  items: [
    { key: "budgeting", title: "Budgeting", completed: false, quiz_score: null },
    { key: "risk", title: "Risk", completed: true, quiz_score: 67 },
  ],
  completed_count: 1,
};

const TOPIC: Topic = {
  key: "budgeting",
  title: "Budgeting",
  explanation: "Deciding where your money goes before you spend it.",
  example: "Income $30,000 split across needs, wants and savings.",
  common_mistake: "Writing an ideal budget you never follow.",
  questions: [
    { question: "Where do you start?", options: ["Copy someone", "Look at last month", "Cut all fun"] },
    { question: "You went over. Now what?", options: ["Ignore it", "Find out why", "Halve it"] },
    { question: "What is 50/30/20?", options: ["Needs, wants, savings", "Rent, food, bus", "Stocks, bonds, cash"] },
  ],
  completed: false,
  quiz_score: null,
};

const api = vi.hoisted(() => ({
  submitted: [] as number[][],
  result: null as QuizResult | null,
}));

vi.mock("../api/learn", () => ({
  listTopics: () => Promise.resolve(LISTING),
  getTopic: () => Promise.resolve(TOPIC),
  submitQuiz: (_key: string, answers: number[]) => {
    api.submitted.push(answers);
    return Promise.resolve(api.result);
  },
}));

function result(marks: boolean[]): QuizResult {
  return {
    answers: marks.map((correct, index) => ({
      correct,
      correct_idx: index === 0 ? 1 : index === 1 ? 1 : 0,
      why: `because of reason ${index + 1}`,
    })),
    correct_count: marks.filter(Boolean).length,
    total: marks.length,
    score: Math.round((marks.filter(Boolean).length / marks.length) * 100),
    completed: true,
    common_mistake: TOPIC.common_mistake,
  };
}

function renderLearn() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Learn />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openBudgeting() {
  fireEvent.click(await screen.findByRole("button", { name: /Budgeting/ }));
  return screen.findByText(TOPIC.explanation);
}

/** Pick an option by its visible label. */
function pick(label: string | RegExp) {
  fireEvent.click(screen.getByRole("radio", { name: label }));
}

beforeEach(() => {
  api.submitted = [];
  api.result = result([true, true, true]);
});

describe("the lesson", () => {
  it("renders the curated content verbatim", async () => {
    renderLearn();
    await openBudgeting();

    expect(screen.getByText(TOPIC.example)).toBeInTheDocument();
    expect(screen.getByText(TOPIC.common_mistake)).toBeInTheDocument();
  });

  it("shows all three questions at once", async () => {
    renderLearn();
    await openBudgeting();

    for (const question of TOPIC.questions) {
      expect(screen.getByText(new RegExp(question.question))).toBeInTheDocument();
    }
  });

  it("groups each question so the choice is announced with it", async () => {
    renderLearn();
    await openBudgeting();

    expect(screen.getAllByRole("group")).toHaveLength(3);
  });
});

describe("answering", () => {
  it("marks nothing until every question is answered", async () => {
    renderLearn();
    await openBudgeting();

    pick("Look at last month");
    pick("Find out why");

    expect(api.submitted).toEqual([]);
    expect(screen.getByRole("button", { name: /check my answers/i })).toBeDisabled();
    expect(screen.getByText(/answer all 3/i)).toBeInTheDocument();
  });

  it("submits all three together, in order", async () => {
    renderLearn();
    await openBudgeting();

    pick("Look at last month");       // index 1
    pick("Find out why");             // index 1
    pick("Needs, wants, savings");    // index 0
    fireEvent.click(screen.getByRole("button", { name: /check my answers/i }));

    await waitFor(() => expect(api.submitted).toEqual([[1, 1, 0]]));
  });

  it("lets an answer be changed before submitting", async () => {
    renderLearn();
    await openBudgeting();

    pick("Copy someone");
    pick("Look at last month");
    pick("Find out why");
    pick("Needs, wants, savings");
    fireEvent.click(screen.getByRole("button", { name: /check my answers/i }));

    await waitFor(() => expect(api.submitted).toEqual([[1, 1, 0]]));
  });

  it("submits once, not once per question", async () => {
    renderLearn();
    await openBudgeting();

    pick("Look at last month");
    pick("Find out why");
    pick("Needs, wants, savings");
    fireEvent.click(screen.getByRole("button", { name: /check my answers/i }));

    await waitFor(() => expect(api.submitted).toHaveLength(1));
  });
});

describe("the result", () => {
  async function completeWith(marks: boolean[]) {
    api.result = result(marks);
    renderLearn();
    await openBudgeting();
    pick("Look at last month");
    pick("Find out why");
    pick("Needs, wants, savings");
    fireEvent.click(screen.getByRole("button", { name: /check my answers/i }));
    return screen.findByRole("status");
  }

  it("reports the count rather than a bare pass or fail", async () => {
    const status = await completeWith([true, false, true]);

    expect(status).toHaveTextContent("2 of 3 right");
  });

  it("explains every question, including the ones that were right", async () => {
    const status = await completeWith([true, false, true]);

    for (const index of [1, 2, 3]) {
      expect(status).toHaveTextContent(`because of reason ${index}`);
    }
  });

  it("names the right option per question", async () => {
    const status = await completeWith([false, false, false]);

    expect(within(status).getByText(/Look at last month/)).toBeInTheDocument();
    expect(within(status).getByText(/Needs, wants, savings/)).toBeInTheDocument();
  });

  it("marks a clean sweep", async () => {
    const status = await completeWith([true, true, true]);

    expect(status).toHaveTextContent("3 of 3 right");
    expect(status).not.toHaveTextContent("Not quite");
  });

  it("can be retried from a blank slate", async () => {
    await completeWith([false, false, false]);

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    expect(screen.getByRole("button", { name: /check my answers/i })).toBeDisabled();
    expect(screen.getAllByRole("radio").every((r) => !(r as HTMLInputElement).checked))
      .toBe(true);
  });
});

describe("the listing", () => {
  it("counts what is done", async () => {
    renderLearn();

    expect(await screen.findByText(/1 of 2 done/)).toBeInTheDocument();
  });

  it("does not call a partial score passed", async () => {
    /** 67 is read, not passed: the row said "passed" for any completed topic
     *  only at a full score, and a partial score must not claim it. */
    renderLearn();

    const row = (await screen.findByRole("button", { name: /Risk/ }));
    expect(row).toHaveTextContent("read");
    expect(row).not.toHaveTextContent("passed");
  });

  it("closes an open lesson and clears its answers", async () => {
    renderLearn();
    await openBudgeting();
    pick("Look at last month");

    fireEvent.click(screen.getByRole("button", { name: /Budgeting/ }));
    fireEvent.click(screen.getByRole("button", { name: /Budgeting/ }));
    await screen.findByText(TOPIC.explanation);

    expect(screen.getByRole("button", { name: /check my answers/i })).toBeDisabled();
  });
});
