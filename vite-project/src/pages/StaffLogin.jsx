import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../services/api";
import ThemeToggle from "../components/ThemeToggle";

export default function StaffLogin() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const response = await api.post("/staff/login", { username, password });
      sessionStorage.removeItem("bankAccount");
      sessionStorage.setItem("staffAuthenticated", "true");
      sessionStorage.setItem("staffRole", response.data.staff.role);
      sessionStorage.setItem("staffUsername", response.data.staff.username);
      navigate("/staff/operations", { replace: true });
    } catch (requestError) {
      setError(
        requestError.response?.data?.message || "Staff sign-in failed."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <ThemeToggle className="auth-theme-toggle" />
      <section className="auth-card">
        <div className="brand-mark">B</div>
        <p className="eyebrow">STAFF ACCESS</p>
        <h1>Staff sign in</h1>
        <p className="muted">
          Authorized staff can access customer support and operations tools.
        </p>
        <form className="form" onSubmit={handleSubmit}>
          <label htmlFor="staff-username">Username</label>
          <input
            id="staff-username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
          <label htmlFor="staff-password">Password</label>
          <input
            id="staff-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {error && <p className="form-message error">{error}</p>}
          <button className="primary-button" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <p className="auth-footer">
          <Link to="/">Return to customer sign in</Link>
        </p>
      </section>
    </main>
  );
}
