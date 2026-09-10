/** A labelled input. Semantic HTML, no styling — the label is the point. */
import type { InputHTMLAttributes } from "react";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
}

export function Field({ label, hint, error, id, ...input }: FieldProps) {
  const fieldId = id ?? `field-${label.toLowerCase().replace(/\W+/g, "-")}`;
  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;

  return (
    <p className="field">
      <label htmlFor={fieldId}>{label}</label>
      <input
        id={fieldId}
        aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
        aria-invalid={error ? true : undefined}
        {...input}
      />
      {hint && <small id={hintId}>{hint}</small>}
      {error && <strong id={errorId} role="alert">{error}</strong>}
    </p>
  );
}
