import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import { useToast } from "../components/Toast";

export default function Transaction({ type }) {
  const isDeposit = type === "deposit";
  const endpoint = isDeposit ? "/deposit" : "/withdraw";

  const [amount, setAmount] = useState("");
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const { showToast } = useToast();

  async function handleSubmit(event) {
    event.preventDefault();

    setMessage("");
    setSuccess(false);

    const numericAmount = Number(amount);

    if (!Number.isFinite(numericAmount) || numericAmount <= 0) {
      const errorMessage = "Enter an amount greater than zero.";

      setMessage(errorMessage);
      showToast(errorMessage, "warning");
      return;
    }

    if (Math.round(numericAmount * 100) !== numericAmount * 100) {
      const errorMessage =
        "Amount can contain a maximum of two decimal places.";

      setMessage(errorMessage);
      showToast(errorMessage, "warning");
      return;
    }

    setLoading(true);

    try {
      const response = await api.post(endpoint, { amount });

      setSuccess(true);
      setMessage(response.data.message);

      const oldAccount = JSON.parse(
        sessionStorage.getItem("bankAccount") || "{}"
      );

      sessionStorage.setItem(
        "bankAccount",
        JSON.stringify({
          ...oldAccount,
          balance: response.data.balance,
        })
      );

      setAmount("");

      showToast(
        response.data.message ||
          `${isDeposit ? "Deposit" : "Withdrawal"} completed successfully.`,
        "success"
      );
    } catch (error) {
      const errorMessage =
        error.response?.data?.message ||
        "Transaction could not be completed.";

      setMessage(errorMessage);
      showToast(errorMessage, "error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">TRANSACTIONS</p>

          <h1>
            {isDeposit ? "Deposit money" : "Withdraw money"}
          </h1>

          <p className="muted">
            {isDeposit
              ? "Add funds to your bank account."
              : "Withdraw funds from your available balance."}
          </p>
        </div>
      </div>

      <div className="transaction-layout">
        <section className="panel transaction-panel">
          <div
            className={`transaction-icon ${
              isDeposit ? "deposit-symbol" : "withdraw-symbol"
            }`}
          >
            {isDeposit ? "＋" : "↗"}
          </div>

          <h2>
            {isDeposit ? "Add money" : "Withdraw money"}
          </h2>

          <p className="muted">
            Enter the amount below. Amounts support up to two decimal
            places.
          </p>

          <form className="form" onSubmit={handleSubmit}>
            <label htmlFor="amount">
              Amount (USD)
            </label>

            <div className="amount-input">
              <span>$</span>

              <input
                id="amount"
                type="number"
                min="0.01"
                step="0.01"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </div>

            {message && (
              <div
                className={`notice ${
                  success ? "success" : "error"
                }`}
              >
                {message}
              </div>
            )}

            <button
              className="primary-button"
              type="submit"
              disabled={loading}
            >
              {loading
                ? "Processing..."
                : isDeposit
                ? "Confirm deposit"
                : "Confirm withdrawal"}
            </button>
          </form>

          <Link className="back-link" to="/dashboard">
            ← Back to dashboard
          </Link>
        </section>

        <aside className="panel tip-panel">
          <span className="tip-icon">ⓘ</span>

          <h3>Before you continue</h3>

          <ul>
            <li>Enter an amount greater than zero.</li>

            <li>
              Use up to two decimal places.
            </li>

            {!isDeposit && (
              <li>
                Withdrawals cannot exceed your available balance.
              </li>
            )}

            <li>
              Wait for the confirmation message before leaving
              this page.
            </li>
          </ul>
        </aside>
      </div>
    </>
  );
}