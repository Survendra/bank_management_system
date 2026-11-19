import { useEffect, useState } from "react";
import {
  getBeneficiaries,
  addBeneficiary,
  updateBeneficiary,
  deleteBeneficiary,
} from "../services/api";
import { useToast } from "../components/useToast";
import ConfirmModal from "../components/ConfirmModal";

export default function Beneficiaries() {
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [deleteId, setDeleteId] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const { showToast } = useToast();

  const [form, setForm] = useState({
    name: "",
    account_number: "",
  });

  const [editingId, setEditingId] = useState(null);

  async function loadBeneficiaries() {
    try {
      setLoading(true);

      const response = await getBeneficiaries();

      setBeneficiaries(response.data.beneficiaries || []);
      setError("");
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

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const response = await getBeneficiaries();
        if (active) {
          setBeneficiaries(response.data.beneficiaries || []);
          setError("");
        }
      } catch (err) {
        if (active) {
          const errorMessage =
            err.response?.data?.message ||
            "Unable to load beneficiaries.";
          setError(errorMessage);
          showToast(errorMessage, "error");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      active = false;
    };
  }, [showToast]);

  function handleChange(e) {
    setForm({
      ...form,
      [e.target.name]: e.target.value,
    });
  }

  function resetForm() {
    setForm({
      name: "",
      account_number: "",
    });

    setEditingId(null);
  }

  async function handleSubmit(e) {
    e.preventDefault();

    setMessage("");
    setError("");

    if (
      !form.name.trim() ||
      !/^\d{11}$/.test(form.account_number)
    ) {
      const errorMessage =
        "Enter a name and a valid 11-digit account number.";

      setError(errorMessage);
      showToast(errorMessage, "warning");
      return;
    }

    try {
      setSaving(true);

      if (editingId) {
        const response = await updateBeneficiary(
          editingId,
          form
        );

        const successMessage =
          response.data.message ||
          "Beneficiary updated successfully.";

        setMessage(successMessage);
        showToast(successMessage, "success");
      } else {
        const response = await addBeneficiary(form);

        const successMessage =
          response.data.message ||
          "Beneficiary added successfully.";

        setMessage(successMessage);
        showToast(successMessage, "success");
      }

      resetForm();

      await loadBeneficiaries();
    } catch (err) {
      const errorMessage =
        err.response?.data?.message ||
        "Unable to save beneficiary.";

      setError(errorMessage);
      showToast(errorMessage, "error");
    } finally {
      setSaving(false);
    }
  }

  function startEdit(beneficiary) {
    setEditingId(beneficiary.beneficiary_id);

    setForm({
      name: beneficiary.name,
      account_number: beneficiary.account_number,
    });

    setMessage("");
    setError("");

    showToast(
      "Beneficiary selected for editing.",
      "info"
    );
  }

  function openDeleteModal(id) {
    setDeleteId(id);
  }

  function closeDeleteModal() {
    if (!deleting) {
      setDeleteId(null);
    }
  }

  async function handleDelete() {
    if (!deleteId) return;

    setMessage("");
    setError("");

    try {
      setDeleting(true);

      const response = await deleteBeneficiary(deleteId);

      const successMessage =
        response.data.message ||
        "Beneficiary deleted successfully.";

      setMessage(successMessage);
      showToast(successMessage, "success");

      setDeleteId(null);

      await loadBeneficiaries();
    } catch (err) {
      const errorMessage =
        err.response?.data?.message ||
        "Unable to delete beneficiary.";

      setError(errorMessage);
      showToast(errorMessage, "error");
    } finally {
      setDeleting(false);
    }
  }

  const beneficiaryToDelete = beneficiaries.find(
    (beneficiary) =>
      beneficiary.beneficiary_id === deleteId
  );

  return (
    <div className="beneficiaries-page">
      <div className="page-heading">
        <div>
          <h1>Beneficiaries</h1>
          <p>
            Manage your saved BlueBank recipients.
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

      <div className="beneficiary-form-card">
        <h2>
          {editingId
            ? "Edit Beneficiary"
            : "Add New Beneficiary"}
        </h2>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Account Holder Name</label>

            <input
              type="text"
              name="name"
              value={form.name}
              onChange={handleChange}
              placeholder="Enter account holder name"
              required
            />
          </div>

          <div className="form-group">
            <label>Account Number</label>

            <input
              type="text"
              name="account_number"
              value={form.account_number}
              onChange={handleChange}
              placeholder="Enter 11-digit account number"
              maxLength={11}
              inputMode="numeric"
              required
            />
          </div>

          <div className="form-actions">
            <button
              type="submit"
              disabled={saving}
            >
              {saving
                ? "Please wait..."
                : editingId
                ? "Update Beneficiary"
                : "Add Beneficiary"}
            </button>

            {editingId && (
              <button
                type="button"
                onClick={resetForm}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      </div>

      <div className="beneficiary-list-card">
        <h2>Saved Beneficiaries</h2>

        {loading ? (
          <p>Loading beneficiaries...</p>
        ) : beneficiaries.length === 0 ? (
          <p>No beneficiaries added yet.</p>
        ) : (
          <div className="beneficiary-list">
            {beneficiaries.map((beneficiary) => (
              <div
                className="beneficiary-item"
                key={beneficiary.beneficiary_id}
              >
                <div className="beneficiary-info">
                  <div className="beneficiary-avatar">
                    {beneficiary.name
                      .charAt(0)
                      .toUpperCase()}
                  </div>

                  <div>
                    <h3>{beneficiary.name}</h3>

                    <p>
                      Account:{" "}
                      {beneficiary.account_number}
                    </p>
                  </div>
                </div>

                <div className="beneficiary-actions">
                  <button
                    onClick={() =>
                      startEdit(beneficiary)
                    }
                  >
                    Edit
                  </button>

                  <button
                    className="delete-button"
                    onClick={() =>
                      openDeleteModal(
                        beneficiary.beneficiary_id
                      )
                    }
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <ConfirmModal
        isOpen={Boolean(deleteId)}
        title="Delete Beneficiary?"
        message={
          beneficiaryToDelete
            ? `Are you sure you want to delete ${beneficiaryToDelete.name}? This action cannot be undone.`
            : "Are you sure you want to delete this beneficiary?"
        }
        confirmText="Delete"
        cancelText="Cancel"
        onConfirm={handleDelete}
        onCancel={closeDeleteModal}
        loading={deleting}
      />
    </div>
  );
}     