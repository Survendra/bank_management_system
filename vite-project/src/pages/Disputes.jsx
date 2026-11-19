import { useEffect, useState } from "react";
import api from "../services/api";
import { useToast } from "../components/useToast";

export default function Disputes() {
  const [disputes, setDisputes] = useState([]);
  const [loading, setLoading] = useState(true);
  const { showToast } = useToast();

  useEffect(() => {
    api.get("/disputes")
      .then((response) => setDisputes(response.data.disputes || []))
      .catch((error) =>
        showToast(
          error.response?.data?.message || "Could not load your disputes.",
          "error"
        )
      )
      .finally(() => setLoading(false));
  }, [showToast]);

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ACCOUNT SUPPORT</p>
          <h1>Transaction disputes</h1>
          <p className="muted">
            Track reported transactions and review the bank’s response.
          </p>
        </div>
      </div>
      <section className="panel feature-panel">
        <h2>Your disputes</h2>
        {loading ? (
          <p className="muted">Loading disputes...</p>
        ) : disputes.length === 0 ? (
          <div className="empty-state">
            <strong>No disputes submitted</strong>
            <p>Open a transaction in your activity and choose “Report a problem”.</p>
          </div>
        ) : (
          <div className="feature-record-list">
            {disputes.map((item) => (
              <article className="feature-record dispute-record" key={item.id}>
                <div>
                  <strong>{item.issue.replaceAll("_", " ")}</strong>
                  <span>
                    Transaction {item.transaction_id} · ${Number(item.amount).toFixed(2)}
                  </span>
                  <small>Submitted {new Date(item.created_at).toLocaleString()}</small>
                  {item.resolution && <small>Resolution: {item.resolution}</small>}
                  {item.reversed && <small>Compensating reversal: {item.reversal_id}</small>}
                </div>
                <span className={`feature-status status-${item.status.toLowerCase()}`}>
                  {item.status.replaceAll("_", " ")}
                </span>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
