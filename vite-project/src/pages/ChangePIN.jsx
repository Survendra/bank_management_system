import { useState } from "react";
import api from "../services/api";

export default function ChangePIN() {
  const [form, setForm] = useState({ current_pin: "", new_pin: "", confirm_pin: "" });
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");
  const [loading, setLoading] = useState(false);

  function update(field, value) {
    setForm((previous) => ({ ...previous, [field]: value.replace(/\D/g, "").slice(0, 4) }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setMessage("");
    setMessageType("");

    if (form.current_pin.length !== 4 || form.new_pin.length !== 4) {
      setMessage("All PIN fields must contain exactly 4 digits.");
      setMessageType("error");
      return;
    }
    if (form.new_pin !== form.confirm_pin) {
      setMessage("New PIN and confirm PIN do not match.");
      setMessageType("error");
      return;
    }
    if (form.current_pin === form.new_pin) {
      setMessage("Your new PIN must be different from your current PIN.");
      setMessageType("error");
      return;
    }

    setLoading(true);
    try {
      const response = await api.post("/change-pin", {
        current_pin: form.current_pin,
        new_pin: form.new_pin,
      });
      setMessage(response.data.message || "PIN changed successfully.");
      setMessageType("success");
      setForm({ current_pin: "", new_pin: "", confirm_pin: "" });
    } catch (error) {
      setMessage(error.response?.data?.message || "Unable to change PIN. Please try again.");
      setMessageType("error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">SECURITY SETTINGS</p>
          <h1>Change PIN</h1>
          <p className="muted">Update the 4-digit PIN used to access your bank account.</p>
        </div>
      </div>

      <div className="change-pin-layout">
        <section className="panel change-pin-panel">
          <div className="change-pin-heading">
            <div className="change-pin-icon">⌑</div>
            <div><h2>Update your PIN</h2><p>Verify your current PIN before choosing a new one.</p></div>
          </div>

          <form className="form" onSubmit={handleSubmit}>
            <label htmlFor="current-pin">Current PIN</label>
            <input id="current-pin" type="password" inputMode="numeric" autoComplete="current-password"
              maxLength={4} placeholder="Enter current 4-digit PIN" value={form.current_pin}
              onChange={(e) => update("current_pin", e.target.value)} required />

            <label htmlFor="new-pin">New PIN</label>
            <input id="new-pin" type="password" inputMode="numeric" autoComplete="new-password"
              maxLength={4} placeholder="Enter new 4-digit PIN" value={form.new_pin}
              onChange={(e) => update("new_pin", e.target.value)} required />

            <label htmlFor="confirm-pin">Confirm new PIN</label>
            <input id="confirm-pin" type="password" inputMode="numeric" autoComplete="new-password"
              maxLength={4} placeholder="Re-enter new PIN" value={form.confirm_pin}
              onChange={(e) => update("confirm_pin", e.target.value)} required />

            {message && <div className={`notice ${messageType}`}>{message}</div>}
            <button className="primary-button" type="submit" disabled={loading}>
              {loading ? "Updating PIN..." : "Change PIN"}
            </button>
          </form>
        </section>

        <aside className="panel pin-guidelines">
          <span className="tip-icon">ⓘ</span>
          <h3>PIN security tips</h3>
          <ul>
            <li>Choose a 4-digit PIN that is difficult to guess.</li>
            <li>Avoid repeated digits such as 1111.</li>
            <li>Avoid simple sequences such as 1234 or 4321.</li>
            <li>Never share your PIN with anyone.</li>
          </ul>
          <div className="pin-security-note">Your PIN is sent to the backend over your local API connection and stored as a salted hash, not as plain text.</div>
        </aside>
      </div>
    </>
  );
}
