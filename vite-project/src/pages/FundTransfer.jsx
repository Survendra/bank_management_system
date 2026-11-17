import { useEffect, useState } from "react";
import { useToast } from "../components/Toast";
import ConfirmModal from "../components/ConfirmModal";
import { getBeneficiaries, transferFunds } from "../services/api";
import { jsPDF } from "jspdf";

export default function FundTransfer() {
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [transferring, setTransferring] = useState(false);

  const [showConfirmModal, setShowConfirmModal] = useState(false);

  const { showToast } = useToast();

  const [form, setForm] = useState({
    beneficiary_id: "",
    amount: "",
    pin: "",
  });

  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [transferDetails, setTransferDetails] = useState(null);

  useEffect(() => {
    async function loadBeneficiaries() {
      try {
        const response = await getBeneficiaries();

        setBeneficiaries(
          response.data.beneficiaries || []
        );
      } catch (err) {
        const errorMessage =
          err.response?.data?.message ||
          "Unable to load beneficiaries.";

        setError(errorMessage);
        showToast(errorMessage, "error");
      } finally {
        setLoading(false);
      }
    }

    loadBeneficiaries();
  }, [showToast]);

  function handleChange(e) {
    setForm((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  }

  function handleSubmit(e) {
    e.preventDefault();

    setMessage("");
    setError("");
    setTransferDetails(null);

    if (!form.beneficiary_id) {
      const message = "Please select a beneficiary.";

      setError(message);
      showToast(message, "warning");
      return;
    }

    const amount = Number(form.amount);

    if (!Number.isFinite(amount) || amount <= 0) {
      const message = "Enter a valid transfer amount.";

      setError(message);
      showToast(message, "warning");
      return;
    }

    if (!/^\d{4}$/.test(form.pin)) {
      const message = "Enter your 4-digit PIN.";

      setError(message);
      showToast(message, "warning");
      return;
    }

    // Validation passed.
    // Open confirmation modal before making the transfer.
    setShowConfirmModal(true);
  }

  function cancelTransfer() {
    if (!transferring) {
      setShowConfirmModal(false);
    }
  }

  async function confirmTransfer() {
    try {
      setTransferring(true);

      const response = await transferFunds({
        beneficiary_id: form.beneficiary_id,
        amount: form.amount,
        pin: form.pin,
      });

      setMessage(response.data.message);
      setTransferDetails(response.data.transfer);

      showToast(
        response.data.message ||
          "Transfer completed successfully.",
        "success"
      );

      setShowConfirmModal(false);

      setForm({
        beneficiary_id: "",
        amount: "",
        pin: "",
      });
    } catch (err) {
      const errorMessage =
        err.response?.data?.message ||
        "Fund transfer failed.";

      setError(errorMessage);
      showToast(errorMessage, "error");

      setShowConfirmModal(false);
    } finally {
      setTransferring(false);
    }
  }

  function downloadReceipt() {
    if (!transferDetails) return;

    const doc = new jsPDF();

    const reference =
      transferDetails.reference ||
      transferDetails.id ||
      "N/A";

    const recipientName =
      transferDetails.recipient_name || "N/A";

    const recipientAccount =
      transferDetails.recipient_account || "N/A";

    const amount = Number(
      transferDetails.amount || 0
    ).toFixed(2);

    const balance = Number(
      transferDetails.sender_balance || 0
    ).toFixed(2);

    const date = new Date().toLocaleString();

    doc.setFontSize(24);
    doc.setFont("helvetica", "bold");
    doc.text("BlueBank", 20, 25);

    doc.setFontSize(11);
    doc.setFont("helvetica", "normal");
    doc.text("Fund Transfer Receipt", 20, 34);

    doc.line(20, 40, 190, 40);

    doc.setFontSize(16);
    doc.setFont("helvetica", "bold");
    doc.text("Transfer Successful", 20, 55);

    doc.setFontSize(11);
    doc.setFont("helvetica", "normal");

    const rows = [
      ["Reference", reference],
      ["Date & Time", date],
      ["Recipient", recipientName],
      ["Recipient Account", recipientAccount],
      ["Amount", `$${amount}`],
      ["Remaining Balance", `$${balance}`],
      ["Status", "Completed"],
    ];

    let y = 72;

    rows.forEach(([label, value]) => {
      doc.setFont("helvetica", "bold");
      doc.text(label, 25, y);

      doc.setFont("helvetica", "normal");
      doc.text(String(value), 85, y);

      y += 12;
    });

    doc.line(20, y + 5, 190, y + 5);

    doc.setFontSize(9);
    doc.text(
      "This is a computer-generated BlueBank transfer receipt.",
      20,
      y + 18
    );

    doc.save(
      `BlueBank-Transfer-${reference}.pdf`
    );
  }

  const selectedBeneficiary = beneficiaries.find(
    (item) =>
      item.beneficiary_id === form.beneficiary_id
  );

  return (
    <div className="fund-transfer-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">PAYMENTS</p>

          <h1>Fund Transfer</h1>

          <p className="muted">
            Transfer money securely to your saved beneficiaries.
          </p>
        </div>
      </div>

      {message && (
        <div className="success-message">
          {message}
        </div>
      )}

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {transferDetails && (
        <div className="transfer-success-card">
          <div className="receipt-success-icon">
            ✓
          </div>

          <h2>Transfer Successful</h2>

          <p>
            <span>Reference</span>

            <strong>
              {transferDetails.reference ||
                transferDetails.id}
            </strong>
          </p>

          <p>
            <span>Recipient</span>

            <strong>
              {transferDetails.recipient_name}
            </strong>
          </p>

          <p>
            <span>Account</span>

            <strong>
              {transferDetails.recipient_account}
            </strong>
          </p>

          <p>
            <span>Amount</span>

            <strong>
              $
              {Number(
                transferDetails.amount
              ).toFixed(2)}
            </strong>
          </p>

          <p>
            <span>Remaining Balance</span>

            <strong>
              $
              {Number(
                transferDetails.sender_balance
              ).toFixed(2)}
            </strong>
          </p>

          <div className="receipt-actions">
            <button
              type="button"
              className="primary-button"
              onClick={downloadReceipt}
            >
              Download Receipt
            </button>

            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                setTransferDetails(null)
              }
            >
              Make Another Transfer
            </button>
          </div>
        </div>
      )}

      {!transferDetails && (
        <div className="transfer-form-card">
          <h2>Transfer Details</h2>

          {loading ? (
            <p className="muted">
              Loading beneficiaries...
            </p>
          ) : beneficiaries.length === 0 ? (
            <div className="empty-transfer-state">
              <div className="empty-icon">
                ＋
              </div>

              <strong>
                No beneficiaries found
              </strong>

              <p>
                Add a beneficiary before making a
                transfer.
              </p>

              <a href="/beneficiaries">
                Add Beneficiary
              </a>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="beneficiary">
                  Select Beneficiary
                </label>

                <select
                  id="beneficiary"
                  name="beneficiary_id"
                  value={form.beneficiary_id}
                  onChange={handleChange}
                  required
                >
                  <option value="">
                    Choose beneficiary
                  </option>

                  {beneficiaries.map(
                    (beneficiary) => (
                      <option
                        key={
                          beneficiary.beneficiary_id
                        }
                        value={
                          beneficiary.beneficiary_id
                        }
                      >
                        {beneficiary.name} -{" "}
                        {beneficiary.account_number}
                      </option>
                    )
                  )}
                </select>
              </div>

              {selectedBeneficiary && (
                <div className="selected-beneficiary">
                  <div className="selected-beneficiary-avatar">
                    {selectedBeneficiary.name
                      .charAt(0)
                      .toUpperCase()}
                  </div>

                  <div>
                    <strong>
                      {selectedBeneficiary.name}
                    </strong>

                    <p>
                      Account{" "}
                      {
                        selectedBeneficiary.account_number
                      }
                    </p>
                  </div>
                </div>
              )}

              <div className="form-group">
                <label htmlFor="amount">
                  Transfer Amount ($)
                </label>

                <input
                  id="amount"
                  type="number"
                  name="amount"
                  value={form.amount}
                  onChange={handleChange}
                  placeholder="0.00"
                  min="0.01"
                  max="5000000000"
                  step="0.01"
                  required
                />
                <p className="muted">
                  Maximum transfer: 500 crore per transaction.
                </p>
              </div>

              <div className="form-group">
                <label htmlFor="pin">
                  Transaction PIN
                </label>

                <input
                  id="pin"
                  type="password"
                  name="pin"
                  value={form.pin}
                  onChange={handleChange}
                  placeholder="Enter your 4-digit PIN"
                  maxLength={4}
                  inputMode="numeric"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={transferring}
              >
                {transferring
                  ? "Processing Transfer..."
                  : "Transfer Money"}
              </button>
            </form>
          )}
        </div>
      )}

      <ConfirmModal
        isOpen={showConfirmModal}
        title="Confirm Fund Transfer"
        message={
          selectedBeneficiary
            ? `Transfer $${Number(form.amount).toFixed(
                2
              )} to ${
                selectedBeneficiary.name
              } (Account ${
                selectedBeneficiary.account_number
              })? Please confirm that the transfer details are correct.`
            : "Are you sure you want to proceed with this transfer?"
        }
        confirmText="Confirm Transfer"
        cancelText="Cancel"
        onConfirm={confirmTransfer}
        onCancel={cancelTransfer}
        loading={transferring}
      />
    </div>
  );
}