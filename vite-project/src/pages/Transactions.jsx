
import { useEffect, useMemo, useState } from "react";
import api from "../services/api";
import { useToast } from "../components/useToast";

export default function Transactions() {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [type, setType] = useState("ALL");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [selectedTransaction, setSelectedTransaction] = useState(null);
  const [disputeIssue, setDisputeIssue] = useState("UNRECOGNIZED");
  const [disputeNotes, setDisputeNotes] = useState("");
  const [disputeSaving, setDisputeSaving] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    api.get("/transactions")
      .then((response) =>
        setTransactions(response.data.transactions || [])
      )
      .catch((err) =>
        setError(
          err.response?.data?.message ||
          "Unable to load transactions."
        )
      )
      .finally(() => setLoading(false));
  }, []);

  function getTransactionInfo(item) {
    switch (item.type) {
      case "DEPOSIT":
        return {
          label: "Deposit",
          title: "Deposit successful",
          icon: "↓",
          category: "credit",
          sign: "+",
          status: "CREDITED",
        };

      case "WITHDRAW":
        return {
          label: "Withdrawal",
          title: "Withdrawal successful",
          icon: "↑",
          category: "debit",
          sign: "−",
          status: "DEBITED",
        };

      case "TRANSFER":
        return {
          label: "Money Sent",
          title: "Transfer successful",
          icon: "↗",
          category: "debit",
          sign: "−",
          status: "SENT",
        };

      case "TRANSFER_RECEIVED":
        return {
          label: "Money Received",
          title: "Transfer received",
          icon: "↙",
          category: "credit",
          sign: "+",
          status: "RECEIVED",
        };

      case "SCHEDULED_TRANSFER":
        return {
          label: "Scheduled transfer",
          title: "Scheduled transfer",
          icon: "◷",
          category: "debit",
          sign: "−",
          status: item.status || "PENDING",
        };

      case "CARD_PAYMENT":
        return {
          label: item.merchant || "Card payment",
          title: "Card payment",
          icon: "▣",
          category: "debit",
          sign: "−",
          status: item.status || "COMPLETED",
        };

      default:
        return {
          label: item.type || "Transaction",
          title: "Transaction details",
          icon: "↔",
          category: "debit",
          sign: "",
          status: item.status || "COMPLETED",
        };
    }
  }

  function formatAmount(value) {
    const amount = Number(value);
    return Number.isFinite(amount) ? amount.toFixed(2) : "0.00";
  }

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? "Date unavailable"
      : date.toLocaleString();
  }

  const filteredTransactions = useMemo(() => {
    const term = search.trim().toLowerCase();

    return transactions.filter((item) => {
      const date = new Date(item.created_at);

      const dateOnly = Number.isNaN(date.getTime())
        ? ""
        : `${date.getFullYear()}-${String(
            date.getMonth() + 1
          ).padStart(2, "0")}-${String(
            date.getDate()
          ).padStart(2, "0")}`;

      return (
        (type === "ALL" || item.type === type) &&
        (!fromDate || (dateOnly && dateOnly >= fromDate)) &&
        (!toDate || (dateOnly && dateOnly <= toDate)) &&
        (
          !term ||
          String(item.id || "").toLowerCase().includes(term) ||
          String(item.type || "").toLowerCase().includes(term) ||
          String(item.amount || "").includes(term) ||
          String(item.description || "").toLowerCase().includes(term) ||
          String(item.reference || "").toLowerCase().includes(term) ||
          String(item.sender_account || "").includes(term) ||
          String(item.recipient_account || "").includes(term)
        )
      );
    });
  }, [transactions, search, type, fromDate, toDate]);

  function clearFilters() {
    setSearch("");
    setType("ALL");
    setFromDate("");
    setToDate("");
  }

  function openTransactionDetails(transaction) {
    setDisputeIssue("UNRECOGNIZED");
    setDisputeNotes("");
    setSelectedTransaction(transaction);
  }

  function closeTransactionDetails() {
    if (disputeSaving) {
      return;
    }

    setSelectedTransaction(null);
    setDisputeIssue("UNRECOGNIZED");
    setDisputeNotes("");
  }

  async function submitDispute() {
    if (!selectedTransaction) {
      return;
    }
    setDisputeSaving(true);
    try {
      const response = await api.post(
        `/transactions/${selectedTransaction.id}/dispute`,
        { issue: disputeIssue, notes: disputeNotes }
      );
      const updated = {
        ...selectedTransaction,
        dispute_id: response.data.dispute.id,
      };
      setSelectedTransaction(updated);
      setTransactions((current) =>
        current.map((item) => item.id === updated.id ? updated : item)
      );
      setDisputeNotes("");
      showToast("Your transaction dispute was submitted.", "success");
    } catch (requestError) {
      showToast(
        requestError.response?.data?.message || "Could not submit this dispute.",
        "error"
      );
    } finally {
      setDisputeSaving(false);
    }
  }

  async function updateCategory(category) {
    if (!selectedTransaction) {
      return;
    }
    try {
      const response = await api.patch(
        `/transactions/${selectedTransaction.id}/category`,
        { category }
      );
      const updated = response.data.transaction;
      setSelectedTransaction(updated);
      setTransactions((current) =>
        current.map((item) => item.id === updated.id ? updated : item)
      );
      showToast("Transaction category updated.", "success");
    } catch (requestError) {
      showToast(
        requestError.response?.data?.message || "Could not update the category.",
        "error"
      );
    }
  }

  const selectedInfo = selectedTransaction
    ? getTransactionInfo(selectedTransaction)
    : null;

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ACCOUNT ACTIVITY</p>
          <h1>Transaction history</h1>
          <p className="muted">
            View and track your deposits, withdrawals and fund transfers.
          </p>
        </div>
      </div>

      <section className="panel history-panel">
        <div className="history-heading">
          <div>
            <h2>Transactions</h2>
            <p>
              Latest activity appears first. Select a transaction
              to view details.
            </p>
          </div>

          <span className="history-count">
            {filteredTransactions.length} of {transactions.length} records
          </span>
        </div>

        {/* Filters */}
        <div className="transaction-filters">
          <div className="filter-search">
            <label htmlFor="txn-search">Search</label>
            <input
              id="txn-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search ID, type, amount or account"
            />
          </div>

          <div>
            <label htmlFor="txn-type">Transaction type</label>
            <select
              id="txn-type"
              value={type}
              onChange={(e) => setType(e.target.value)}
            >
              <option value="ALL">All transactions</option>
              <option value="DEPOSIT">Deposits</option>
              <option value="WITHDRAW">Withdrawals</option>
              <option value="TRANSFER">Money sent</option>
              <option value="TRANSFER_RECEIVED">Money received</option>
            </select>
          </div>

          <div>
            <label htmlFor="from-date">From date</label>
            <input
              id="from-date"
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
            />
          </div>

          <div>
            <label htmlFor="to-date">To date</label>
            <input
              id="to-date"
              type="date"
              min={fromDate || undefined}
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
            />
          </div>

          <button
            type="button"
            className="clear-filters"
            onClick={clearFilters}
          >
            Clear filters
          </button>
        </div>

        {loading && <p className="muted">Loading transactions...</p>}

        {error && <div className="notice error">{error}</div>}

        {!loading && !error && filteredTransactions.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">⌕</div>
            <strong>
              {transactions.length
                ? "No matching transactions"
                : "No transactions yet"}
            </strong>
            <p>
              {transactions.length
                ? "Try changing or clearing your filters."
                : "Your banking activity will appear here."}
            </p>
          </div>
        )}

        {/* Transaction table */}
        {!loading && filteredTransactions.length > 0 && (
          <div className="table-wrap">
            <table className="transaction-table">
              <thead>
                <tr>
                  <th>TRANSACTION</th>
                  <th>DATE & TIME</th>
                  <th>AMOUNT</th>
                  <th>STATUS</th>
                  <th>BALANCE AFTER</th>
                </tr>
              </thead>

              <tbody>
                {filteredTransactions.map((item) => {
                  const info = getTransactionInfo(item);
                  const date = new Date(item.created_at);

                  return (
                    <tr
                      key={item.id}
                      className="transaction-row"
                      tabIndex={0}
                      role="button"
                      aria-label={`View ${info.label} transaction ${item.id}`}
                      onClick={() => openTransactionDetails(item)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openTransactionDetails(item);
                        }
                      }}
                    >
                      <td>
                        <div className="transaction-name">
                          <span className={`table-icon ${info.category}`}>
                            {info.icon}
                          </span>

                          <div>
                            <strong>{info.label}</strong>
                            <small>{item.id}</small>
                          </div>
                        </div>
                      </td>

                      <td>
                        <span className="date-cell">
                          {Number.isNaN(date.getTime())
                            ? "Date unavailable"
                            : date.toLocaleDateString()}
                          <small>
                            {Number.isNaN(date.getTime())
                              ? ""
                              : date.toLocaleTimeString()}
                          </small>
                        </span>
                      </td>

                      <td>
                        <strong className={`${info.category}-text`}>
                          {info.sign}${formatAmount(item.amount)}
                        </strong>
                      </td>

                      <td>
                        <span className={`feature-status status-${String(item.status || "COMPLETED").toLowerCase()}`}>
                          {String(item.status || "COMPLETED").replaceAll("_", " ")}
                        </span>
                      </td>

                      <td className="balance-cell">
                        ${formatAmount(item.balance_after)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Transaction details popup */}
      {selectedTransaction && (
        <div
          className="transaction-modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) {
              closeTransactionDetails();
            }
          }}
          role="presentation"
        >
          <section
            className="transaction-detail-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="transaction-detail-title"
          >
            <button
              className="modal-close"
              type="button"
              aria-label="Close transaction details"
              onClick={closeTransactionDetails}
              disabled={disputeSaving}
            >
              ×
            </button>

            <div className={`detail-status-icon ${selectedInfo.category}`}>
              {selectedInfo.icon}
            </div>

            <p className="eyebrow">TRANSACTION DETAILS</p>

            <h2 id="transaction-detail-title">
              {selectedInfo.title}
            </h2>

            <p className="detail-amount">
              {selectedInfo.sign}$
              {formatAmount(selectedTransaction.amount)}
            </p>

            <span className={`detail-type-pill ${selectedInfo.category}`}>
              {String(selectedTransaction.status || "COMPLETED").replaceAll("_", " ")}
            </span>

            <div className="detail-divider"></div>

            <div className="detail-fields">
              <div>
                <span>Transaction ID</span>
                <strong>{selectedTransaction.id}</strong>
              </div>

              <div>
                <span>Transaction type</span>
                <strong>{selectedInfo.label}</strong>
              </div>

              <div>
                <span>Date & time</span>
                <strong>{formatDate(selectedTransaction.created_at)}</strong>
              </div>

              <div>
                <span>Amount</span>
                <strong>${formatAmount(selectedTransaction.amount)}</strong>
              </div>

              {(selectedTransaction.reference ||
                selectedTransaction.type === "TRANSFER" ||
                selectedTransaction.type === "TRANSFER_RECEIVED") && (
                <div>
                  <span>Transfer reference</span>
                  <strong>
                    {selectedTransaction.reference || selectedTransaction.id}
                  </strong>
                </div>
              )}

              {selectedTransaction.description && (
                <div>
                  <span>Description</span>
                  <strong>{selectedTransaction.description}</strong>
                </div>
              )}

              {selectedTransaction.recipient_account && (
                <div>
                  <span>Recipient account</span>
                  <strong>{selectedTransaction.recipient_account}</strong>
                </div>
              )}

              {selectedTransaction.sender_account && (
                <div>
                  <span>Sender account</span>
                  <strong>{selectedTransaction.sender_account}</strong>
                </div>
              )}

              <div>
                <span>Balance after transaction</span>
                <strong>
                  ${formatAmount(selectedTransaction.balance_after)}
                </strong>
              </div>

              <div>
                <span>Status</span>
                <strong className="status-complete">
                  {String(selectedTransaction.status || "COMPLETED").replaceAll("_", " ")}
                </strong>
              </div>
            </div>

            <label className="transaction-category-control">
              Spending category
              <select
                value={selectedTransaction.category || "Other"}
                onChange={(event) => updateCategory(event.target.value)}
              >
                {["Bills", "Education", "Entertainment", "Food", "Health", "Shopping", "Transport", "Travel", "Other"].map((category) => (
                  <option key={category}>{category}</option>
                ))}
              </select>
            </label>

            {selectedTransaction.dispute_id ? (
              <a className="view-all-link dispute-track-link" href="/disputes">
                Track your dispute
              </a>
            ) : selectedTransaction.status === "COMPLETED" || !selectedTransaction.status ? (
              <div className="dispute-form">
                <strong>Something wrong with this transaction?</strong>
                <label>
                  Reason
                  <select
                    value={disputeIssue}
                    onChange={(event) => setDisputeIssue(event.target.value)}
                  >
                    <option value="UNRECOGNIZED">I do not recognize this transaction</option>
                    <option value="DUPLICATE">Duplicate transaction</option>
                    <option value="INCORRECT_AMOUNT">Incorrect amount</option>
                    <option value="OTHER">Other</option>
                  </select>
                </label>
                <label>
                  Notes (optional)
                  <textarea
                    maxLength={500}
                    value={disputeNotes}
                    onChange={(event) => setDisputeNotes(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={disputeSaving}
                  onClick={submitDispute}
                >
                  {disputeSaving ? "Submitting..." : "Report a problem"}
                </button>
              </div>
            ) : null}

            <button
              className="primary-button detail-done"
              type="button"
              onClick={closeTransactionDetails}
              disabled={disputeSaving}
            >
              Done
            </button>
          </section>
        </div>
      )}
    </>
  );
}
