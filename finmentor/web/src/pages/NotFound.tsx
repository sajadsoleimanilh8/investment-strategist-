import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <section>
      <h2>Not found</h2>
      <p className="muted">
        That page does not exist. <Link to="/dashboard">Back to the dashboard</Link>.
      </p>
    </section>
  );
}
