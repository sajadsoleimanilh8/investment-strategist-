/**
 * The multi-step wizard that turns a signed-up user into an onboarded one.
 *
 * Four steps, and nothing is sent until the last. A half-finished profile is
 * worse than none — the health score would read it as real and report a
 * savings rate built from an income with no expenses yet.
 *
 * The same shape as the Telegram onboarding conversation, deliberately: same
 * questions, same order, same `FinancialProfileIn` payload at the end.
 */
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { saveProfile } from "../api/profile";
import { createGoal } from "../api/goals";
import { Field } from "../components/Field";
import { FormError } from "../components/FormError";
import { useAuth } from "../auth/AuthContext";
import { EXPENSE_CATEGORIES, type ExpenseBreakdown } from "../api/types";

const STEPS = ["Income", "Spending", "Position", "First goal"] as const;

const EMPTY_EXPENSES: ExpenseBreakdown = {
  housing: 0, food: 0, transportation: 0, education: 0,
  bills: 0, entertainment: 0, shopping: 0, other: 0,
};

/** Blank means zero. An empty box is "I do not spend on this", not an error. */
function toNumber(value: string): number {
  const parsed = Number(value.replace(/[,\s]/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

export function Onboarding() {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState(0);
  const [income, setIncome] = useState("");
  const [incomeType, setIncomeType] = useState("fixed");
  const [expenses, setExpenses] = useState<Record<string, string>>({});
  const [savings, setSavings] = useState("");
  const [debt, setDebt] = useState("");
  const [debtPayment, setDebtPayment] = useState("");
  const [emergencyFund, setEmergencyFund] = useState("");
  const [riskProfile, setRiskProfile] = useState("moderate");
  const [goalName, setGoalName] = useState("");
  const [goalTarget, setGoalTarget] = useState("");
  const [goalCurrent, setGoalCurrent] = useState("");
  const [goalDeadline, setGoalDeadline] = useState("");
  const [goalPriority, setGoalPriority] = useState(3);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function next(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (step === 0 && toNumber(income) <= 0) {
      setError("Income needs to be a number above zero.");
      return;
    }
    if (step === 2 && [savings, debt, debtPayment, emergencyFund]
        .some((value) => toNumber(value) < 0)) {
      setError("These cannot be negative.");
      return;
    }
    if (step < STEPS.length - 1) {
      setStep(step + 1);
      return;
    }
    void finish();
  }

  async function finish() {
    if (!user) return;
    setBusy(true);
    setError(null);
    try {
      await saveProfile(user.id, {
        monthly_income: toNumber(income),
        income_type: incomeType,
        expenses: EXPENSE_CATEGORIES.reduce(
          (all, key) => ({ ...all, [key]: toNumber(expenses[key] ?? "") }),
          { ...EMPTY_EXPENSES },
        ),
        current_savings: toNumber(savings),
        debt: toNumber(debt),
        monthly_debt_payment: toNumber(debtPayment),
        emergency_fund: toNumber(emergencyFund),
        risk_profile: riskProfile,
      });

      if (goalName.trim() && toNumber(goalTarget) > 0) {
        await createGoal(user.id, {
          name: goalName.trim(),
          target_amount: toNumber(goalTarget),
          current_amount: toNumber(goalCurrent),
          deadline: goalDeadline || null,
          priority: goalPriority,
        });
      }

      await refreshUser();
      navigate("/", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save that.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2>Set up your profile</h2>
      <p>
        Step {step + 1} of {STEPS.length}: {STEPS[step]}. Nothing is saved until
        the last step.
      </p>

      <form onSubmit={next}>
        {step === 0 && (
          <fieldset>
            <legend>What comes in</legend>
            <Field label="Monthly income" inputMode="numeric" value={income}
                   required onChange={(e) => setIncome(e.target.value)} />
            <p className="field">
              <label htmlFor="income-type">Is it steady?</label>
              <select id="income-type" value={incomeType}
                      onChange={(e) => setIncomeType(e.target.value)}>
                <option value="fixed">Fixed</option>
                <option value="variable">Variable</option>
                <option value="mixed">A mix</option>
              </select>
            </p>
          </fieldset>
        )}

        {step === 1 && (
          <fieldset>
            <legend>What goes out each month</legend>
            <p>Leave anything you do not spend on blank.</p>
            {EXPENSE_CATEGORIES.map((category) => (
              <Field
                key={category}
                label={category[0].toUpperCase() + category.slice(1)}
                inputMode="numeric"
                value={expenses[category] ?? ""}
                onChange={(e) =>
                  setExpenses({ ...expenses, [category]: e.target.value })}
              />
            ))}
          </fieldset>
        )}

        {step === 2 && (
          <fieldset>
            <legend>Where you stand</legend>
            <Field label="Total savings" inputMode="numeric" value={savings}
                   onChange={(e) => setSavings(e.target.value)} />
            <Field label="Total debt" inputMode="numeric" value={debt}
                   hint="0 if none." onChange={(e) => setDebt(e.target.value)} />
            <Field label="Monthly debt payment" inputMode="numeric" value={debtPayment}
                   onChange={(e) => setDebtPayment(e.target.value)} />
            <Field label="Emergency fund" inputMode="numeric" value={emergencyFund}
                   hint="The part of your savings set aside for the unexpected."
                   onChange={(e) => setEmergencyFund(e.target.value)} />
            <p className="field">
              <label htmlFor="risk">How do you feel about ups and downs?</label>
              <select id="risk" value={riskProfile}
                      onChange={(e) => setRiskProfile(e.target.value)}>
                <option value="conservative">I would rather keep what I have</option>
                <option value="moderate">Some movement is fine</option>
                <option value="aggressive">I can sit through big swings</option>
              </select>
              <small>
                This changes how I talk to you about risk. It is not a
                suitability assessment and it is not advice.
              </small>
            </p>
          </fieldset>
        )}

        {step === 3 && (
          <fieldset>
            <legend>Something to aim at (optional)</legend>
            <Field label="What are you saving for?" value={goalName}
                   hint="Leave blank to skip — you can add one any time."
                   onChange={(e) => setGoalName(e.target.value)} />
            <Field label="What does it cost?" inputMode="numeric" value={goalTarget}
                   onChange={(e) => setGoalTarget(e.target.value)} />
            <Field label="Put aside so far" inputMode="numeric" value={goalCurrent}
                   onChange={(e) => setGoalCurrent(e.target.value)} />
            <Field label="Want it by" type="date" value={goalDeadline}
                   onChange={(e) => setGoalDeadline(e.target.value)} />
            <p className="field">
              <label htmlFor="priority">How important is it?</label>
              <select id="priority" value={goalPriority}
                      onChange={(e) => setGoalPriority(Number(e.target.value))}>
                <option value={1}>1 — highest</option>
                <option value={2}>2</option>
                <option value={3}>3 — normal</option>
                <option value={4}>4</option>
                <option value={5}>5 — lowest</option>
              </select>
            </p>
          </fieldset>
        )}

        <FormError message={error} />

        <div className="actions">
          {step > 0 && (
            <button type="button" onClick={() => setStep(step - 1)} disabled={busy}>
              Back
            </button>
          )}
          <button type="submit" disabled={busy}>
            {step < STEPS.length - 1 ? "Next" : busy ? "Saving…" : "Finish"}
          </button>
        </div>
      </form>
    </section>
  );
}
