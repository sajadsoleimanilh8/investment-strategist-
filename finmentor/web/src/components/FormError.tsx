/** One place errors are announced, so a screen reader always hears them. */
export function FormError({ message }: { message?: string | null }) {
  if (!message) return null;
  return <p role="alert" className="form-error">{message}</p>;
}
