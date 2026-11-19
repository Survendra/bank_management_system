import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../services/api";
import { useToast } from "../components/useToast";

export default function StaffDisputes() {
  const [disputes, setDisputes] = useState([]);
  const [filter, setFilter] = useState("OPEN");
  const [notes, setNotes] = useState({});
  const [reverse, setReverse] = useState({});
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState("");
  const filterRef = useRef(filter);
  const { showToast } = useToast();
  const navigate = useNavigate();
  const canReview = ["admin", "reviewer"].includes(
    sessionStorage.getItem("staffRole")
  );

  useEffect(() => {
    let active = true;
    api.get("/staff/disputes", {
      params: filter === "ALL" ? {} : { status: filter },
    })
      .then((response) => {
        if (active) {
          setDisputes(response.data.disputes || []);
        }
      })
      .catch((error) => {
        if (error.response?.status === 401 || error.response?.status === 403) {
          sessionStorage.removeItem("staffAuthenticated");
          sessionStorage.removeItem("staffRole");
          sessionStorage.removeItem("staffUsername");
          navigate("/staff", { replace: true });
          return;
        }
        showToast(
          error.response?.data?.message || "Could not load dispute queue.",
          "error"
        );
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [filter, navigate, showToast]);

  async function review(dispute, action) {
    const resolution = (notes[dispute.id] || "").trim();
    if (action !== "UNDER_REVIEW" && !resolution) {
      showToast("Add review notes before resolving or declining a dispute.", "warning");
      return;
    }

    setWorkingId(dispute.id);
    try {
      const response = await api.patch(`/staff/disputes/${dispute.id}`, {
        action,
        resolution,
        reverse_transfer: action === "RESOLVED" && Boolean(reverse[dispute.id]),
      });
      const updated = response.data.dispute;
      const activeFilter = filterRef.current;
      setDisputes((current) => {
        const matchesFilter = activeFilter === "ALL" || activeFilter === updated.status;
        const exists = current.some((item) => item.id === updated.id);
        if (!matchesFilter) {
          return current.filter((item) => item.id !== updated.id);
        }
        return exists
          ? current.map((item) => item.id === updated.id ? updated : item)
          : [updated, ...current];
      });
      showToast(`Dispute marked ${action.toLowerCase().replaceAll("_", " ")}.`, "success");
    } catch (error) {
      if (!error.response) {
        try {
          const response = await api.get("/staff/disputes");
          const persisted = (response.data.disputes || []).find(
            (item) => item.id === dispute.id,
          );
          if (persisted?.status === action) {
            const activeFilter = filterRef.current;
            setDisputes((current) => {
              const matchesFilter = activeFilter === "ALL" || activeFilter === persisted.status;
              if (!matchesFilter) {
                return current.filter((item) => item.id !== persisted.id);
              }
              return [persisted, ...current.filter((item) => item.id !== persisted.id)];
            });
            showToast(`Dispute marked ${action.toLowerCase().replaceAll("_", " ")}.`, "success");
            return;
          }
        } catch (reconcileError) {
          showToast(
            reconcileError.response?.data?.message ||
              "Could not confirm whether the dispute update was saved.",
            "error",
          );
          return;
        }
      }
      showToast(
        error.response?.data?.message || "Could not update this dispute.",
        "error"
      );
    } finally {
      setWorkingId("");
    }
  }

  async function logout() {
    try {
      await api.post("/logout");
    } catch (error) {
      showToast(
        error.response?.data?.message || "Could not securely end staff session.",
        "error"
      );
      return;
    }
    sessionStorage.removeItem("staffAuthenticated");
    sessionStorage.removeItem("staffRole");
    sessionStorage.removeItem("staffUsername");
    navigate("/staff", { replace: true });
  }

  return (
    <main className="staff-page staff-disputes-page">
      <header className="staff-header">
        <div className="staff-header-brand">
          <span className="staff-brand-mark" aria-hidden="true">B</span>
          <div className="staff-header-copy">
            <p className="eyebrow staff-eyebrow">BLUEBANK OPERATIONS</p>
            <h1>Dispute review</h1>
            <p className="muted">Review customer reports and record an auditable resolution.</p>
            <nav className="staff-nav" aria-label="Staff pages">
              <Link to="/staff/operations">Operations</Link>
              <Link to="/staff/disputes" aria-current="page">Disputes</Link>
            </nav>
          </div>
        </div>
        <button type="button" className="secondary-button staff-signout" onClick={logout}>
          Sign out
        </button>
      </header>
      <section className="panel feature-panel">
        <div className="staff-queue-heading">
          <div>
            <h2>Review queue</h2>
            <p>Filter cases by status. Closing a case requires review notes.</p>
          </div>
          <div className="staff-filter">
            <label htmlFor="dispute-filter">Queue</label>
            <select
              id="dispute-filter"
              value={filter}
              onChange={(event) => {
                filterRef.current = event.target.value;
                setDisputes([]);
                setLoading(true);
                setFilter(event.target.value);
              }}
              disabled={Boolean(workingId)}
            >
              <option value="OPEN">Open</option>
              <option value="UNDER_REVIEW">Under review</option>
              <option value="RESOLVED">Resolved</option>
              <option value="DECLINED">Declined</option>
              <option value="ALL">All disputes</option>
            </select>
          </div>
        </div>
        {loading ? (
          <p className="muted" role="status">Loading disputes...</p>
        ) : disputes.length === 0 ? (
          <div className="empty-state">
            <strong>Queue is clear</strong>
            <p>No disputes match this status.</p>
          </div>
        ) : (
          <div className="staff-dispute-list">
            {disputes.map((dispute) => {
              const isOpen = ["OPEN", "UNDER_REVIEW"].includes(dispute.status);
              const isTransfer = ["TRANSFER", "TRANSFER_RECEIVED"].includes(
                dispute.transaction_type
              );
              return (
                <article className="staff-dispute-card" key={dispute.id}>
                  <div className="feature-record">
                    <div>
                      <strong>{dispute.issue.replaceAll("_", " ")}</strong>
                      <span>
                        {dispute.transaction_type} · ${Number(dispute.amount).toFixed(2)}
                      </span>
                      <small>
                        {dispute.account_number_masked} · {dispute.transaction_id}
                      </small>
                      <small>Submitted {new Date(dispute.created_at).toLocaleString()}</small>
                      {dispute.notes && <p>{dispute.notes}</p>}
                    </div>
                    <span className={`feature-status status-${dispute.status.toLowerCase()}`}>
                      {dispute.status.replaceAll("_", " ")}
                    </span>
                  </div>
                  {isOpen && canReview && (
                    <div className="staff-review-controls">
                      <label>
                        Review notes
                        <textarea
                          aria-describedby={`review-note-hint-${dispute.id}`}
                          maxLength={500}
                          value={notes[dispute.id] || ""}
                          onChange={(event) =>
                            setNotes((current) => ({
                              ...current,
                              [dispute.id]: event.target.value,
                            }))
                          }
                        />
                        <small id={`review-note-hint-${dispute.id}`} className="staff-review-hint">
                          Required to resolve or decline this dispute.
                        </small>
                      </label>
                      {dispute.status === "OPEN" && (
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={workingId === dispute.id}
                          onClick={() => review(dispute, "UNDER_REVIEW")}
                        >
                          Start review
                        </button>
                      )}
                      {isTransfer && (
                        <label className="reverse-confirm">
                          <input
                            type="checkbox"
                            checked={Boolean(reverse[dispute.id])}
                            onChange={(event) =>
                              setReverse((current) => ({
                                ...current,
                                [dispute.id]: event.target.checked,
                              }))
                            }
                          />
                          Resolve with a compensating transfer reversal
                        </label>
                      )}
                      <div className="staff-review-actions">
                        <button
                          type="button"
                          className="primary-button"
                          disabled={workingId === dispute.id || !notes[dispute.id]?.trim()}
                          onClick={() => review(dispute, "RESOLVED")}
                        >
                          Resolve
                        </button>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={workingId === dispute.id || !notes[dispute.id]?.trim()}
                          onClick={() => review(dispute, "DECLINED")}
                        >
                          Decline
                        </button>
                      </div>
                    </div>
                  )}
                  {dispute.reversed && (
                    <p className="muted">Reversal reference: {dispute.reversal_id}</p>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
