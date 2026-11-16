import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../services/api";

export default function ForgotPIN() {
  const [accountNumber, setAccountNumber] = useState("");
  const [code, setCode] = useState("");
  const [newPin, setNewPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");

  const [step, setStep] = useState(1);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();

  async function handleAccountSubmit(event) {
    event.preventDefault();
    setMessage("");

    if (accountNumber.length !== 11) {
      setMessage("Enter your 11-digit account number.");
      return;
    }

    setLoading(true);

    try {
      await api.post("/forgot-pin", {
        account_number: accountNumber,
      });

      setStep(2);
    } catch (error) {
      setMessage(
        error.response?.data?.message ||
          "Unable to verify the account."
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleCodeSubmit(event) {
    event.preventDefault();
    setMessage("");

    if (code.length !== 6) {
      setMessage("Enter the 6-digit Google Authenticator code.");
      return;
    }

    setLoading(true);

    try {
      await api.post("/forgot-pin/verify-2fa", {
        account_number: accountNumber,
        code,
      });

      setStep(3);
    } catch (error) {
      setMessage(
        error.response?.data?.message ||
          "Invalid authenticator code."
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleResetSubmit(event) {
    event.preventDefault();
    setMessage("");

    if (newPin.length !== 4) {
      setMessage("New PIN must contain exactly 4 digits.");
      return;
    }

    if (newPin !== confirmPin) {
      setMessage("PINs do not match.");
      return;
    }

    setLoading(true);

    try {
      await api.post("/reset-pin", {
        account_number: accountNumber,
        new_pin: newPin,
      });

      setStep(4);
    } catch (error) {
      setMessage(
        error.response?.data?.message ||
          "Unable to reset your PIN."
      );
    } finally {
      setLoading(false);
    }
  }

  function goToLogin() {
    navigate("/");
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="brand-mark">B</div>

        {step === 1 && (
          <>
            <p className="eyebrow">ACCOUNT RECOVERY</p>

            <h1>Forgot your PIN?</h1>

            <p className="muted">
              Enter your BlueBank account number to begin
              PIN recovery.
            </p>

            <form
              onSubmit={handleAccountSubmit}
              className="form"
            >
              <label htmlFor="accountNumber">
                Account number
              </label>

              <input
                id="accountNumber"
                inputMode="numeric"
                autoComplete="username"
                maxLength={11}
                placeholder="Enter your 11-digit account number"
                value={accountNumber}
                onChange={(event) =>
                  setAccountNumber(
                    event.target.value.replace(/\D/g, "")
                  )
                }
                required
              />

              {message && (
                <p className="form-message error">
                  {message}
                </p>
              )}

              <button
                className="primary-button"
                type="submit"
                disabled={loading}
              >
                {loading
                  ? "Checking..."
                  : "Continue"}
              </button>
            </form>
          </>
        )}

        {step === 2 && (
          <>
            <p className="eyebrow">
              TWO-FACTOR AUTHENTICATION
            </p>

            <h1>Verify your identity</h1>

            <p className="muted">
              Open Google Authenticator and enter the
              6-digit code for your BlueBank account.
            </p>

            <form
              onSubmit={handleCodeSubmit}
              className="form"
            >
              <label htmlFor="authenticatorCode">
                Authentication code
              </label>

              <input
                id="authenticatorCode"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="Enter 6-digit code"
                value={code}
                onChange={(event) =>
                  setCode(
                    event.target.value.replace(/\D/g, "")
                  )
                }
                required
              />

              {message && (
                <p className="form-message error">
                  {message}
                </p>
              )}

              <button
                className="primary-button"
                type="submit"
                disabled={
                  loading || code.length !== 6
                }
              >
                {loading
                  ? "Verifying..."
                  : "Verify code"}
              </button>
            </form>
          </>
        )}

        {step === 3 && (
          <>
            <p className="eyebrow">RESET PIN</p>

            <h1>Set a new PIN</h1>

            <p className="muted">
              Create a new secure 4-digit PIN for your
              BlueBank account.
            </p>

            <form
              onSubmit={handleResetSubmit}
              className="form"
            >
              <label htmlFor="newPin">
                New PIN
              </label>

              <input
                id="newPin"
                type="password"
                inputMode="numeric"
                autoComplete="new-password"
                maxLength={4}
                placeholder="Enter new 4-digit PIN"
                value={newPin}
                onChange={(event) =>
                  setNewPin(
                    event.target.value.replace(/\D/g, "")
                  )
                }
                required
              />

              <label htmlFor="confirmPin">
                Confirm new PIN
              </label>

              <input
                id="confirmPin"
                type="password"
                inputMode="numeric"
                autoComplete="new-password"
                maxLength={4}
                placeholder="Re-enter new 4-digit PIN"
                value={confirmPin}
                onChange={(event) =>
                  setConfirmPin(
                    event.target.value.replace(/\D/g, "")
                  )
                }
                required
              />

              {message && (
                <p className="form-message error">
                  {message}
                </p>
              )}

              <button
                className="primary-button"
                type="submit"
                disabled={
                  loading ||
                  newPin.length !== 4 ||
                  confirmPin.length !== 4
                }
              >
                {loading
                  ? "Resetting..."
                  : "Reset PIN"}
              </button>
            </form>
          </>
        )}

        {step === 4 && (
          <>
            <p className="eyebrow">
              PIN RESET COMPLETE
            </p>

            <h1>PIN reset successfully</h1>

            <p className="muted">
              Your BlueBank PIN has been changed. You
              can now sign in using your new PIN.
            </p>

            <button
              className="primary-button"
              type="button"
              onClick={goToLogin}
            >
              Back to sign in
            </button>
          </>
        )}

        {step !== 4 && (
          <p className="auth-footer">
            <Link to="/">Back to sign in</Link>
          </p>
        )}
      </section>
    </main>
  );
}