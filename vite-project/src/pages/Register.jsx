import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../services/api";
import ThemeToggle from "../components/ThemeToggle";

export default function Register() {
  const [form, setForm] = useState({ name: "", age: "", pin: "", confirmPin: "" });
  const [message, setMessage] = useState("");
  const [createdAccount, setCreatedAccount] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  function update(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setMessage("");
    setCreatedAccount("");

    if (form.pin !== form.confirmPin) {
      setMessage("PIN and confirm PIN do not match.");
      return;
    }

    setLoading(true);
    try {
      const response = await api.post("/register", {
        name: form.name.trim(),
        age: Number(form.age),
        pin: form.pin,
      });
      setCreatedAccount(response.data.account_number);
      setForm({ name: "", age: "", pin: "", confirmPin: "" });
    } catch (error) {
      setMessage(error.response?.data?.message || "Unable to create account.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <ThemeToggle className="auth-theme-toggle" />
      <section className="auth-card">
        <div className="brand-mark">B</div>
        <p className="eyebrow">GET STARTED</p>
        <h1>Create your account</h1>
        <p className="muted">Enter your details to open a new bank account.</p>

        <form onSubmit={handleSubmit} className="form">
          <label htmlFor="name">Full name</label>
          <input id="name" name="name" value={form.name} onChange={update}
            placeholder="Enter your full name" autoComplete="name" required />

          <label htmlFor="age">Age</label>
          <input id="age" name="age" type="number" min="18" max="120"
            value={form.age} onChange={update} placeholder="Enter your age" required />

          <label htmlFor="pin">Create 4-digit PIN</label>
          <input id="pin" name="pin" type="password" inputMode="numeric"
            maxLength={4} value={form.pin} onChange={(e) => setForm({ ...form, pin: e.target.value.replace(/\D/g, "") })}
            placeholder="Choose a strong PIN" autoComplete="new-password" required />

          <label htmlFor="confirmPin">Confirm PIN</label>
          <input id="confirmPin" name="confirmPin" type="password" inputMode="numeric"
            maxLength={4} value={form.confirmPin} onChange={(e) => setForm({ ...form, confirmPin: e.target.value.replace(/\D/g, "") })}
            placeholder="Re-enter your PIN" autoComplete="new-password" required />

          {message && <p className="form-message error">{message}</p>}
          {createdAccount && (
            <div className="success-panel">
              <strong>Account created successfully!</strong>
              <span>Your account number is:</span>
              <strong className="account-number">{createdAccount}</strong>
              <span>Save this number. You will need it to sign in.</span>
              <button type="button" className="text-button" onClick={() => navigate("/")}>
                Go to sign in
              </button>
            </div>
          )}
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="auth-footer">
          Already have an account? <Link to="/">Sign in</Link>
        </p>
      </section>
    </main>
  );
}
