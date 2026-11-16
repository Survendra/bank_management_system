import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../services/api";

export default function Login() {
  const [accountNumber, setAccountNumber] = useState("");
  const [pin, setPin] = useState("");
  const [twoFactorCode, setTwoFactorCode] = useState("");
  const [requires2FA, setRequires2FA] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    setMessage("");
    setLoading(true);

    try {
      const response = await api.post("/login", {
        account_number: accountNumber,
        pin,
      });

      if (response.data.requires_2fa) {
        setRequires2FA(true);
        setMessage("");
        return;
      }

      sessionStorage.setItem(
        "bankAccount",
        JSON.stringify(response.data.account)
      );

      navigate("/dashboard");
    } catch (error) {
      setMessage(
        error.response?.data?.message ||
          "Unable to login. Check that the backend is running."
      );
    } finally {
      setLoading(false);
    }
  }

  async function handle2FAVerification(event) {
    event.preventDefault();
    setMessage("");
    setLoading(true);

    try {
      const response = await api.post("/login/verify-2fa", {
        code: twoFactorCode,
      });

      sessionStorage.setItem(
        "bankAccount",
        JSON.stringify(response.data.account)
      );

      navigate("/dashboard");
    } catch (error) {
      setMessage(
        error.response?.data?.message ||
          "Invalid authenticator code."
      );
    } finally {
      setLoading(false);
    }
  }

  function handleBackToLogin() {
    setRequires2FA(false);
    setTwoFactorCode("");
    setMessage("");
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="brand-mark">B</div>

        {!requires2FA ? (
          <>
            <p className="eyebrow">WELCOME BACK</p>
            <h1>Sign in to your account</h1>
            <p className="muted">
              Access your account and manage your money.
            </p>

            <form onSubmit={handleSubmit} className="form">
              <label htmlFor="accountNumber">Account number</label>
              <input
                id="accountNumber"
                inputMode="numeric"
                autoComplete="username"
                maxLength={11}
                placeholder="Enter your 11-digit account number"
                value={accountNumber}
                onChange={(e) =>
                  setAccountNumber(
                    e.target.value.replace(/\D/g, "")
                  )
                }
                required
              />

              <label htmlFor="pin">4-digit PIN</label>
              <input
                id="pin"
                type="password"
                inputMode="numeric"
                autoComplete="current-password"
                maxLength={4}
                placeholder="Enter your PIN"
                value={pin}
                onChange={(e) =>
                  setPin(e.target.value.replace(/\D/g, ""))
                }
                required
              />

              {message && (
                <p className="form-message error">{message}</p>
              )}

              <button
                className="primary-button"
                type="submit"
                disabled={loading}
              >
                {loading ? "Signing in..." : "Sign in"}
              </button>
            </form>

           <div className="auth-footer">
              <p>
                <Link to="/forgot-pin">Forgot your PIN?</Link>
              </p>

              <p>
                Don't have an account?{" "}
                <Link to="/register">
                  Create an account
                </Link>
              </p>
            </div>
          </>
        ) : (
          <>
            <p className="eyebrow">TWO-FACTOR AUTHENTICATION</p>
            <h1>Verify your identity</h1>

            <p className="muted">
              Open Google Authenticator and enter the 6-digit
              verification code for your BlueBank account.
            </p>

            <form
              onSubmit={handle2FAVerification}
              className="form"
            >
              <label htmlFor="twoFactorCode">
                Authentication code
              </label>

              <input
                id="twoFactorCode"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="Enter 6-digit code"
                value={twoFactorCode}
                onChange={(e) =>
                  setTwoFactorCode(
                    e.target.value.replace(/\D/g, "")
                  )
                }
                required
              />

              {message && (
                <p className="form-message error">{message}</p>
              )}

              <button
                className="primary-button"
                type="submit"
                disabled={loading}
              >
                {loading ? "Verifying..." : "Verify & Sign in"}
              </button>
            </form>

            <button
              type="button"
              className="secondary-button"
              onClick={handleBackToLogin}
              disabled={loading}
            >
              ← Back to login
            </button>
          </>
        )}
      </section>
    </main>
  );
}