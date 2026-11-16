import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";

export default function Dashboard() {
  const [account, setAccount] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadDashboard() {
      try {
        const [accountResponse, transactionResponse] =
          await Promise.all([
            api.get("/account"),
            api.get("/transactions"),
          ]);

        setAccount(accountResponse.data.account);
        setTransactions(
          transactionResponse.data.transactions || []
        );

        sessionStorage.setItem(
          "bankAccount",
          JSON.stringify(accountResponse.data.account)
        );
      } catch (err) {
        setError(
          err.response?.data?.message ||
            "Could not load dashboard. Please sign in again."
        );
      }
    }

    loadDashboard();
  }, []);

  const summary = useMemo(() => {
    return transactions.reduce(
      (totals, item) => {
        const amount = Number(item.amount) || 0;

        if (item.type === "DEPOSIT") {
          totals.deposits += amount;
        }

        if (item.type === "WITHDRAW") {
          totals.withdrawals += amount;
        }

        return totals;
      },
      { deposits: 0, withdrawals: 0 }
    );
  }, [transactions]);

  if (error) {
    return <div className="notice error">{error}</div>;
  }

  if (!account) {
    return (
      <>
        <div className="page-heading">
          <div>
            <div className="skeleton skeleton-eyebrow"></div>
            <div className="skeleton skeleton-title"></div>
            <div className="skeleton skeleton-subtitle"></div>
          </div>
        </div>

        <div className="summary-grid">
          <article className="balance-card dashboard-skeleton-card">
            <div className="skeleton skeleton-balance-label"></div>
            <div className="skeleton skeleton-balance"></div>
            <div className="skeleton skeleton-account"></div>
          </article>

          <article className="info-card dashboard-skeleton-card">
            <div className="skeleton skeleton-icon"></div>
            <div className="skeleton skeleton-label"></div>
            <div className="skeleton skeleton-amount"></div>
            <div className="skeleton skeleton-small"></div>
          </article>

          <article className="info-card dashboard-skeleton-card">
            <div className="skeleton skeleton-icon"></div>
            <div className="skeleton skeleton-label"></div>
            <div className="skeleton skeleton-amount"></div>
            <div className="skeleton skeleton-small"></div>
          </article>
        </div>

        <div className="section-title">
          <div>
            <div className="skeleton skeleton-section-title"></div>
            <div className="skeleton skeleton-section-subtitle"></div>
          </div>
        </div>

        <div className="action-grid">
          {[1, 2, 3, 4, 5].map((item) => (
            <div
              key={item}
              className="action-card dashboard-skeleton-action"
            >
              <div className="skeleton skeleton-action-icon"></div>
              <div className="skeleton skeleton-action-title"></div>
              <div className="skeleton skeleton-action-text"></div>
              <div className="skeleton skeleton-action-arrow"></div>
            </div>
          ))}
        </div>

        <div className="section-title">
          <div>
            <div className="skeleton skeleton-section-title"></div>
            <div className="skeleton skeleton-section-subtitle"></div>
          </div>
        </div>

        <section className="panel recent-panel">
          <div className="dashboard-table-skeleton">
            {[1, 2, 3, 4, 5].map((item) => (
              <div
                key={item}
                className="dashboard-table-row-skeleton"
              >
                <div className="skeleton skeleton-row-main"></div>
                <div className="skeleton skeleton-row-date"></div>
                <div className="skeleton skeleton-row-amount"></div>
                <div className="skeleton skeleton-row-balance"></div>
              </div>
            ))}
          </div>
        </section>
      </>
    );
  }

  const recentTransactions = transactions.slice(0, 5);

  function getTransactionInfo(item) {
    if (item.type === "DEPOSIT") {
      return {
        label: "Deposit",
        icon: "↓",
        category: "credit",
        sign: "+",
      };
    }

    if (item.type === "WITHDRAW") {
      return {
        label: "Withdrawal",
        icon: "↑",
        category: "debit",
        sign: "−",
      };
    }

    if (item.type === "TRANSFER") {
      return {
        label: "Money Sent",
        icon: "↗",
        category: "debit",
        sign: "−",
      };
    }

    if (item.type === "TRANSFER_RECEIVED") {
      return {
        label: "Money Received",
        icon: "↙",
        category: "credit",
        sign: "+",
      };
    }

    return {
      label: item.type || "Transaction",
      icon: "↔",
      category: "debit",
      sign: "",
    };
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">OVERVIEW</p>

          <h1>Your dashboard</h1>

          <p className="muted">
            Here is a summary of your bank account and recent activity.
          </p>
        </div>
      </div>

      <div className="summary-grid">
        <article className="balance-card">
          <div className="balance-card-top">
            <span>Available balance</span>
            <span className="balance-icon">$</span>
          </div>

          <h2>${Number(account.balance).toFixed(2)}</h2>

          <p>
            Account ending in{" "}
            {account.account_number.slice(-4)}
          </p>
        </article>

        <article className="info-card">
          <span className="info-icon blue">↓</span>

          <span className="info-label">
            Total deposits
          </span>

          <strong className="credit-text">
            ${summary.deposits.toFixed(2)}
          </strong>

          <small>
            Based on recorded transactions
          </small>
        </article>

        <article className="info-card">
          <span className="info-icon mint">↑</span>

          <span className="info-label">
            Total withdrawals
          </span>

          <strong className="debit-text">
            ${summary.withdrawals.toFixed(2)}
          </strong>

          <small>
            Based on recorded transactions
          </small>
        </article>
      </div>

      <div className="section-title">
        <div>
          <h2>Quick actions</h2>
          <p>Manage your money with ease.</p>
        </div>
      </div>

      <div className="action-grid">
        <Link to="/transfer" className="action-card">
          <span className="action-symbol transfer-symbol">
            ⇄
          </span>

          <strong>Fund transfer</strong>

          <span>
            Send money to a beneficiary
          </span>

          <b>→</b>
        </Link>

        <Link
          to="/beneficiaries"
          className="action-card"
        >
          <span className="action-symbol beneficiary-symbol">
            ♙
          </span>

          <strong>Beneficiaries</strong>

          <span>
            Manage your saved recipients
          </span>

          <b>→</b>
        </Link>

        <Link
          to="/deposit"
          className="action-card"
        >
          <span className="action-symbol deposit-symbol">
            ＋
          </span>

          <strong>Deposit money</strong>

          <span>
            Add funds to your account
          </span>

          <b>→</b>
        </Link>

        <Link
          to="/withdraw"
          className="action-card"
        >
          <span className="action-symbol withdraw-symbol">
            ↗
          </span>

          <strong>Withdraw money</strong>

          <span>
            Take money out of your account
          </span>

          <b>→</b>
        </Link>

        <Link
          to="/transactions"
          className="action-card"
        >
          <span className="action-symbol details-symbol">
            ↔
          </span>

          <strong>Transactions</strong>

          <span>
            Review your account activity
          </span>

          <b>→</b>
        </Link>
      </div>

      <div className="section-title">
        <div>
          <h2>Recent transactions</h2>

          <p>
            Your five latest account activities.
          </p>
        </div>

        <Link
          className="view-all-link"
          to="/transactions"
        >
          View all →
        </Link>
      </div>

      <section className="panel recent-panel">
        {recentTransactions.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">↔</div>

            <strong>
              No transactions yet
            </strong>

            <p>
              Your banking activities will appear here.
            </p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="transaction-table">
              <thead>
                <tr>
                  <th>TRANSACTION</th>
                  <th>DATE & TIME</th>
                  <th>AMOUNT</th>
                  <th>BALANCE AFTER</th>
                </tr>
              </thead>

              <tbody>
                {recentTransactions.map((item) => {
                  const info =
                    getTransactionInfo(item);

                  const date = new Date(
                    item.created_at
                  );

                  return (
                    <tr key={item.id}>
                      <td>
                        <div className="transaction-name">
                          <span
                            className={`table-icon ${info.category}`}
                          >
                            {info.icon}
                          </span>

                          <div>
                            <strong>
                              {info.label}
                            </strong>

                            <small>
                              {item.id}
                            </small>
                          </div>
                        </div>
                      </td>

                      <td>
                        <span className="date-cell">
                          {date.toLocaleDateString()}

                          <small>
                            {date.toLocaleTimeString()}
                          </small>
                        </span>
                      </td>

                      <td>
                        <strong
                          className={`${info.category}-text`}
                        >
                          {info.sign}$
                          {Number(
                            item.amount
                          ).toFixed(2)}
                        </strong>
                      </td>

                      <td className="balance-cell">
                        $
                        {Number(
                          item.balance_after
                        ).toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="dashboard-note">
        <span>🔒</span>

        <div>
          <strong>
            Your account is protected
          </strong>

          <p>
            Never share your PIN or account credentials
            with anyone.
          </p>
        </div>
      </div>
    </>
  );
}