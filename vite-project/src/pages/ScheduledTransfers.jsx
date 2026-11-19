import { useEffect, useState } from "react";
import api from "../services/api";
import { useToast } from "../components/useToast";

const initialForm = {
  beneficiary_id: "",
  amount: "",
  scheduled_for: "",
  frequency: "ONCE",
  pin: "",
};

export default function ScheduledTransfers() {
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { showToast } = useToast();

  async function loadData() {
    try {
      const [beneficiaryResponse, scheduleResponse] = await Promise.all([
        api.get("/beneficiaries"),
        api.get("/scheduled-transfers"),
      ]);
      const items = beneficiaryResponse.data.beneficiaries || [];
      setBeneficiaries(items);
      setSchedules(scheduleResponse.data.scheduled_transfers || []);
      setForm((current) => ({
        ...current,
        beneficiary_id: current.beneficiary_id || items[0]?.beneficiary_id || "",
      }));
    } catch (error) {
      showToast(
        error.response?.data?.message || "Could not load scheduled transfers.",
        "error"
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get("/beneficiaries"),
      api.get("/scheduled-transfers"),
    ])
      .then(([beneficiaryResponse, scheduleResponse]) => {
        if (!active) {
          return;
        }
        const items = beneficiaryResponse.data.beneficiaries || [];
        setBeneficiaries(items);
        setSchedules(scheduleResponse.data.scheduled_transfers || []);
        setForm((current) => ({
          ...current,
          beneficiary_id: current.beneficiary_id || items[0]?.beneficiary_id || "",
        }));
      })
      .catch((error) =>
        showToast(
          error.response?.data?.message || "Could not load scheduled transfers.",
          "error"
        )
      )
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [showToast]);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await api.post("/scheduled-transfers", {
        ...form,
        scheduled_for: new Date(form.scheduled_for).toISOString(),
      });
      setForm((current) => ({ ...initialForm, beneficiary_id: current.beneficiary_id }));
      showToast("Your transfer has been scheduled.", "success");
      await loadData();
    } catch (error) {
      showToast(
        error.response?.data?.message || "Could not schedule this transfer.",
        "error"
      );
    } finally {
      setSaving(false);
    }
  }

  async function cancelSchedule(scheduleId) {
    try {
      await api.delete(`/scheduled-transfers/${scheduleId}`);
      showToast("Scheduled transfer cancelled.", "success");
      await loadData();
    } catch (error) {
      showToast(
        error.response?.data?.message || "Could not cancel this transfer.",
        "error"
      );
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PAYMENTS</p>
          <h1>Scheduled transfers</h1>
          <p className="muted">
            Set up one-time or recurring payments and follow their status.
          </p>
        </div>
      </div>

      <section className="panel feature-panel">
        <h2>Schedule a transfer</h2>
        {beneficiaries.length === 0 ? (
          <div className="notice">
            Add a beneficiary before creating a scheduled transfer.
          </div>
        ) : (
          <form className="feature-form" onSubmit={handleSubmit}>
            <label>
              Beneficiary
              <select
                value={form.beneficiary_id}
                onChange={(event) =>
                  setForm({ ...form, beneficiary_id: event.target.value })
                }
                required
              >
                {beneficiaries.map((item) => (
                  <option key={item.beneficiary_id} value={item.beneficiary_id}>
                    {item.name} ····{item.account_number.slice(-4)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Amount
              <input
                type="number"
                min="0.01"
                max="5000000000"
                step="0.01"
                value={form.amount}
                onChange={(event) =>
                  setForm({ ...form, amount: event.target.value })
                }
                required
              />
            </label>
            <label>
              First transfer
              <input
                type="datetime-local"
                value={form.scheduled_for}
                onChange={(event) =>
                  setForm({ ...form, scheduled_for: event.target.value })
                }
                required
              />
            </label>
            <label>
              Frequency
              <select
                value={form.frequency}
                onChange={(event) =>
                  setForm({ ...form, frequency: event.target.value })
                }
              >
                <option value="ONCE">One time</option>
                <option value="WEEKLY">Weekly</option>
                <option value="MONTHLY">Monthly</option>
              </select>
            </label>
            <label>
              Confirm with PIN
              <input
                type="password"
                inputMode="numeric"
                maxLength={4}
                value={form.pin}
                onChange={(event) =>
                  setForm({ ...form, pin: event.target.value.replace(/\D/g, "") })
                }
                required
              />
            </label>
            <button className="primary-button" disabled={saving}>
              {saving ? "Scheduling..." : "Schedule transfer"}
            </button>
          </form>
        )}
      </section>

      <section className="panel feature-panel feature-list-panel">
        <div className="history-heading">
          <div>
            <h2>Transfer schedule history</h2>
            <p>Pending, completed, failed and recurring transfers.</p>
          </div>
        </div>
        {loading ? (
          <p className="muted">Loading schedules...</p>
        ) : schedules.length === 0 ? (
          <div className="empty-state">
            <strong>No scheduled transfers</strong>
            <p>Your upcoming payments will appear here.</p>
          </div>
        ) : (
          <div className="feature-record-list">
            {schedules.map((item) => (
              <article className="feature-record" key={item.id}>
                <div>
                  <strong>{item.recipient_name}</strong>
                  <span>{item.frequency.toLowerCase()} · ${Number(item.amount).toFixed(2)}</span>
                  <small>
                    {item.status === "ACTIVE" ? "Next: " : "Last run: "}
                    {new Date(item.status === "ACTIVE" ? item.next_run_at : item.last_run_at || item.created_at).toLocaleString()}
                  </small>
                </div>
                <span className={`feature-status status-${item.status.toLowerCase()}`}>
                  {item.status}
                </span>
                {item.status === "ACTIVE" && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => cancelSchedule(item.id)}
                  >
                    Cancel
                  </button>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
