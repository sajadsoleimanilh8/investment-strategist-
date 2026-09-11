/**
 * The editable profile.
 *
 * `GET /api/financial-profile/{id}` returns the *derived* twin, not the raw
 * row, so this page seeds its form from the twin's own inputs — income,
 * expenses, position — and sends back a full `FinancialProfileIn`. A PUT is a
 * replace, not a patch, so every field has to be present.
 */
import { type FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getProfile, saveProfile } from "../api/profile";
import { AsyncBoundary, messageFor } from "../components/AsyncBoundary";
import { Field } from "../components/Field";
import { FormError } from "../components/FormError";
import { EXPENSE_CATEGORIES, type ExpenseBreakdown } from "../api/types";
import { useAuth } from "../auth/AuthContext";

const BLANK: ExpenseBreakdown = {
  housing: 0, food: 0, transportation: 0, education: 0,
  bills: 0, entertainment: 0, shopping: 0, other: 0,
};

export function Profile() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<{
    income: string;
    incomeType: string;
    expenses: ExpenseBreakdown;
    savings: string;
    debt: string;
    debtPayment: string;
    emergencyFund: string;
    riskProfile: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const profile = useQuery({
    queryKey: ["profile", user?.id],
    queryFn: () => getProfile(user!.id),
    enabled: Boolean(user),
  });

  useEffect(() => {
    if (!profile.data || form) return;
    setForm({
      income: String(profile.data.income),
      incomeType: "fixed",
      expenses: { ...BLANK, ...profile.data.expenses },
      savings: String(profile.data.current_savings),
      debt: String(profile.data.debt),
      debtPayment: String(profile.data.monthly_debt_payment),
      emergencyFund: String(profile.data.emergency_fund),
      riskProfile: profile.data.risk_profile,
    });
  }, [profile.data, form]);

  const save = useMutation({
    mutationFn: () =>
      saveProfile(user!.id, {
        monthly_income: Number(form!.income),
        income_type: form!.incomeType,
        expenses: form!.expenses,
        current_savings: Number(form!.savings),
        debt: Number(form!.debt),
        monthly_debt_payment: Number(form!.debtPayment),
        emergency_fund: Number(form!.emergencyFund),
        risk_profile: form!.riskProfile,
      }),
    onSuccess: () => {
      setSaved(true);
      // Changing income or spending moves every figure downstream.
      queryClient.invalidateQueries({ queryKey: ["summary"] });
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
    onError: (caught) => setError(messageFor(caught)),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    if (!form || Number(form.income) <= 0) {
      setError("Income needs to be above zero.");
      return;
    }
    save.mutate();
  }

  return (
    <section>
      <h2>Your profile</h2>
      <AsyncBoundary isLoading={profile.isLoading} error={profile.error}>
        {form && (
          <form onSubmit={submit}>
            <fieldset>
              <legend>Income</legend>
              <Field
                label="Monthly income"
                inputMode="numeric"
                value={form.income}
                onChange={(e) => setForm({ ...form, income: e.target.value })}
              />
            </fieldset>

            <fieldset>
              <legend>Monthly spending</legend>
              {EXPENSE_CATEGORIES.map((category) => (
                <Field
                  key={category}
                  label={category[0].toUpperCase() + category.slice(1)}
                  inputMode="numeric"
                  value={String(form.expenses[category] ?? 0)}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      expenses: { ...form.expenses, [category]: Number(e.target.value || 0) },
                    })
                  }
                />
              ))}
            </fieldset>

            <fieldset>
              <legend>Position</legend>
              <Field
                label="Total savings"
                inputMode="numeric"
                value={form.savings}
                onChange={(e) => setForm({ ...form, savings: e.target.value })}
              />
              <Field
                label="Total debt"
                inputMode="numeric"
                value={form.debt}
                onChange={(e) => setForm({ ...form, debt: e.target.value })}
              />
              <Field
                label="Monthly debt payment"
                inputMode="numeric"
                value={form.debtPayment}
                onChange={(e) => setForm({ ...form, debtPayment: e.target.value })}
              />
              <Field
                label="Emergency fund"
                inputMode="numeric"
                value={form.emergencyFund}
                onChange={(e) => setForm({ ...form, emergencyFund: e.target.value })}
              />
              <p className="field">
                <label htmlFor="risk-profile">Risk profile</label>
                <select
                  id="risk-profile"
                  value={form.riskProfile}
                  onChange={(e) => setForm({ ...form, riskProfile: e.target.value })}
                >
                  <option value="conservative">Conservative</option>
                  <option value="moderate">Moderate</option>
                  <option value="aggressive">Aggressive</option>
                </select>
              </p>
            </fieldset>

            <FormError message={error} />
            {saved && <p role="status">Saved.</p>}

            <div className="actions">
              <button type="submit" disabled={save.isPending}>
                {save.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        )}
      </AsyncBoundary>
    </section>
  );
}
