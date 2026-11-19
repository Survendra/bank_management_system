import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../services/api";

const emptyPage = { page: 1, page_size: 25, total: 0, pages: 0 };
const initialTransactionForm = {
  q: "",
  account_number: "",
  type: "",
  status: "",
  from: "",
  to: "",
  min_amount: "",
  max_amount: "",
};
const initialAuditForm = {
  actor: "",
  action: "",
  entity_id: "",
  from: "",
  to: "",
};
const staffRoleInfo = [
  {
    value: "admin",
    label: "Administrator",
    access: "Manage staff accounts, account flags, and dispute reviews.",
  },
  {
    value: "support",
    label: "Support",
    access: "Review customer accounts and manage internal account flags.",
  },
  {
    value: "reviewer",
    label: "Dispute reviewer",
    access: "Review and resolve customer disputes.",
  },
  {
    value: "read_only",
    label: "Read only",
    access: "View operational data, transactions, and audit history.",
  },
];

function messageFrom(error, fallback) {
  return error.response?.data?.message || fallback;
}

function formatDate(value) {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString();
}

function formatAmount(value) {
  const amount = Number(value);
  return Number.isFinite(amount) ? `$${amount.toFixed(2)}` : "Amount unavailable";
}

function StatusBadge({ status }) {
  const label = String(status || "UNKNOWN").replaceAll("_", " ");
  const className = String(status || "unknown").toLowerCase().replaceAll("_", "-");
  return <span className={`staff-status-badge status-${className}`}>{label}</span>;
}

export default function StaffOperations() {
  const [tab, setTab] = useState("dashboard");
  const [summary, setSummary] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [recentFlags, setRecentFlags] = useState([]);
  const [staff, setStaff] = useState({
    username: sessionStorage.getItem("staffUsername") || "Staff",
    role: sessionStorage.getItem("staffRole") || "read_only",
  });
  const [error, setError] = useState("");
  const [customers, setCustomers] = useState([]);
  const [customerPage, setCustomerPage] = useState(emptyPage);
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerSearch, setCustomerSearch] = useState("");
  const [selectedRef, setSelectedRef] = useState("");
  const [flags, setFlags] = useState([]);
  const [customersLoading, setCustomersLoading] = useState(false);
  const [flagReason, setFlagReason] = useState("");
  const [resolutions, setResolutions] = useState({});
  const [working, setWorking] = useState(false);
  const [transactions, setTransactions] = useState([]);
  const [transactionsLoading, setTransactionsLoading] = useState(false);
  const [transactionPage, setTransactionPage] = useState(emptyPage);
  const [transactionFilters, setTransactionFilters] = useState({});
  const [transactionForm, setTransactionForm] = useState(initialTransactionForm);
  const [auditEntries, setAuditEntries] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditPage, setAuditPage] = useState(emptyPage);
  const [auditFilters, setAuditFilters] = useState({});
  const [auditForm, setAuditForm] = useState(initialAuditForm);
  const [staffUsers, setStaffUsers] = useState([]);
  const [staffUsersLoading, setStaffUsersLoading] = useState(false);
  const [staffAccountSaving, setStaffAccountSaving] = useState(false);
  const [staffAccountMessage, setStaffAccountMessage] = useState("");
  const [staffActionSaving, setStaffActionSaving] = useState("");
  const [staffActionMessage, setStaffActionMessage] = useState("");
  const [passwordResetTarget, setPasswordResetTarget] = useState("");
  const [passwordResetForm, setPasswordResetForm] = useState({
    password: "",
    confirmPassword: "",
  });
  const [staffAccountForm, setStaffAccountForm] = useState({
    username: "",
    password: "",
    confirmPassword: "",
    role: "support",
  });
  const navigate = useNavigate();

  const handleApiError = useCallback((requestError, fallback) => {
    if (
      requestError.response?.status === 401 ||
      requestError.response?.status === 403
    ) {
      sessionStorage.removeItem("staffAuthenticated");
      sessionStorage.removeItem("staffRole");
      sessionStorage.removeItem("staffUsername");
      navigate("/staff", { replace: true });
      return;
    }
    setError(messageFrom(requestError, fallback));
  }, [navigate]);

  const loadDashboard = useCallback(async () => {
    setDashboardLoading(true);
    try {
      const response = await api.get("/staff/dashboard");
      setSummary(response.data.summary);
      setRecentFlags(response.data.recent_flags || []);
    } catch (requestError) {
      handleApiError(requestError, "Could not load operations summary.");
    } finally {
      setDashboardLoading(false);
    }
  }, [handleApiError]);

  useEffect(() => {
    let active = true;
    api.get("/staff/me")
      .then((response) => {
        if (!active) return;
        setStaff(response.data.staff);
        sessionStorage.setItem("staffRole", response.data.staff.role);
        sessionStorage.setItem("staffUsername", response.data.staff.username);
      })
      .catch((requestError) => handleApiError(requestError, "Could not verify staff access."));
    api.get("/staff/dashboard")
      .then((response) => {
        if (!active) return;
        setSummary(response.data.summary);
        setRecentFlags(response.data.recent_flags || []);
      })
      .catch((requestError) =>
        handleApiError(requestError, "Could not load operations summary.")
      )
      .finally(() => {
        if (active) setDashboardLoading(false);
      });
    return () => {
      active = false;
    };
  }, [handleApiError, loadDashboard]);

  async function loadCustomers(page = 1, query = customerSearch, preserveSelection = false) {
    setError("");
    setCustomersLoading(true);
    try {
      const response = await api.get("/staff/customers", {
        params: { q: query, page },
      });
      setCustomers(response.data.customers || []);
      setCustomerPage(response.data.pagination || emptyPage);
      if (!preserveSelection) {
        setSelectedRef("");
        setFlags([]);
      }
    } catch (requestError) {
      handleApiError(requestError, "Could not search customer accounts.");
    } finally {
      setCustomersLoading(false);
    }
  }

  async function openCustomer(customer) {
    if (selectedRef === customer.account_ref) {
      setSelectedRef("");
      return;
    }
    setSelectedRef(customer.account_ref);
    setFlags([]);
    setFlagReason("");
    setError("");
    try {
      const response = await api.get(
        `/staff/accounts/${customer.account_ref}/flags`
      );
      setFlags(response.data.flags || []);
    } catch (requestError) {
      handleApiError(requestError, "Could not load account flags.");
    }
  }

  async function refreshFlags() {
    const response = await api.get(`/staff/accounts/${selectedRef}/flags`);
    const currentFlags = response.data.flags || [];
    setFlags(currentFlags);
    return currentFlags;
  }

  async function reconcileFlagChange(requestError, isApplied, message) {
    if (requestError.response) {
      return "not-applied";
    }

    try {
      const currentFlags = await refreshFlags();
      if (!currentFlags.some(isApplied)) {
        return "not-applied";
      }
      await Promise.all([
        loadCustomers(customerPage.page, customerSearch, true),
        loadDashboard(),
      ]);
      return "applied";
    } catch (reconcileError) {
      handleApiError(reconcileError, message);
      return "unknown";
    }
  }

  async function createFlag(event) {
    event.preventDefault();
    if (!selectedRef || !flagReason.trim()) return;
    const reason = flagReason.trim();
    setWorking(true);
    setError("");
    try {
      await api.post(`/staff/accounts/${selectedRef}/flags`, {
        reason,
      });
      setFlagReason("");
      await refreshFlags();
      await loadCustomers(customerPage.page, customerSearch, true);
      await loadDashboard();
    } catch (requestError) {
      const reconciled = await reconcileFlagChange(
        requestError,
        (flag) => flag.status === "ACTIVE" && flag.reason === reason,
        "Could not verify whether the account flag was saved.",
      );
      if (reconciled === "applied") {
        setFlagReason("");
        return;
      }
      if (reconciled === "unknown") return;
      handleApiError(requestError, "Could not flag this account.");
    } finally {
      setWorking(false);
    }
  }

  async function resolveFlag(flagId) {
    const resolution = (resolutions[flagId] || "").trim();
    if (!selectedRef || !resolution) return;
    setWorking(true);
    setError("");
    try {
      await api.patch(
        `/staff/accounts/${selectedRef}/flags/${flagId}`,
        { resolution }
      );
      await refreshFlags();
      setResolutions((current) => ({ ...current, [flagId]: "" }));
      await loadCustomers(customerPage.page, customerSearch, true);
      await loadDashboard();
    } catch (requestError) {
      const reconciled = await reconcileFlagChange(
        requestError,
        (flag) =>
          flag.id === flagId &&
          flag.status === "RESOLVED" &&
          flag.resolution === resolution,
        "Could not verify whether the account flag was resolved.",
      );
      if (reconciled === "applied") {
        setResolutions((current) => ({ ...current, [flagId]: "" }));
        return;
      }
      if (reconciled === "unknown") return;
      handleApiError(requestError, "Could not resolve this account flag.");
    } finally {
      setWorking(false);
    }
  }

  async function loadTransactions(page = 1, filters = transactionFilters) {
    setError("");
    setTransactionsLoading(true);
    try {
      const params = Object.fromEntries(
        Object.entries({ ...filters, page }).filter(([, value]) => value !== "")
      );
      const response = await api.get("/staff/transactions", { params });
      setTransactions(response.data.transactions || []);
      setTransactionPage(response.data.pagination || emptyPage);
      setTransactionFilters(filters);
    } catch (requestError) {
      handleApiError(requestError, "Could not search transactions.");
    } finally {
      setTransactionsLoading(false);
    }
  }

  async function loadAudit(page = 1, filters = auditFilters) {
    setError("");
    setAuditLoading(true);
    try {
      const params = Object.fromEntries(
        Object.entries({ ...filters, page }).filter(([, value]) => value !== "")
      );
      const response = await api.get("/staff/audit-log", { params });
      setAuditEntries(response.data.entries || []);
      setAuditPage(response.data.pagination || emptyPage);
      setAuditFilters(filters);
    } catch (requestError) {
      handleApiError(requestError, "Could not load the staff audit timeline.");
    } finally {
      setAuditLoading(false);
    }
  }

  async function loadStaffUsers() {
    setError("");
    setStaffUsersLoading(true);
    try {
      const response = await api.get("/staff/users");
      setStaffUsers(response.data.staff_users || []);
    } catch (requestError) {
      handleApiError(requestError, "Could not load staff accounts.");
    } finally {
      setStaffUsersLoading(false);
    }
  }

  async function resetStaffPassword(event, user) {
    event.preventDefault();
    setError("");
    setStaffActionMessage("");
    if (passwordResetForm.password !== passwordResetForm.confirmPassword) {
      setError("The password and confirmation do not match.");
      return;
    }

    setStaffActionSaving(user.id);
    try {
      const response = await api.post(
        `/staff/users/${encodeURIComponent(user.id)}/password`,
        { password: passwordResetForm.password },
      );
      setPasswordResetForm({ password: "", confirmPassword: "" });
      setPasswordResetTarget("");
      setStaffActionMessage(response.data.message || "Staff password reset.");
      await loadStaffUsers();
    } catch (requestError) {
      handleApiError(requestError, "Could not reset the staff password.");
    } finally {
      setStaffActionSaving("");
    }
  }

  async function changeStaffAccess(user, action) {
    const isRevoking = action === "revoke";
    const confirmation = isRevoking
      ? `Revoke access for ${user.username}? Their active sessions will be ended.`
      : `Reactivate access for ${user.username}?`;
    if (!window.confirm(confirmation)) return;

    setError("");
    setStaffActionMessage("");
    setStaffActionSaving(user.id);
    try {
      const response = await api.post(
        `/staff/users/${encodeURIComponent(user.id)}/${action}`,
      );
      setStaffActionMessage(response.data.message || "Staff access updated.");
      await loadStaffUsers();
    } catch (requestError) {
      handleApiError(
        requestError,
        isRevoking ? "Could not revoke staff access." : "Could not reactivate staff access.",
      );
    } finally {
      setStaffActionSaving("");
    }
  }

  async function createStaffAccount(event) {
    event.preventDefault();
    setError("");
    setStaffAccountMessage("");

    if (staffAccountForm.password !== staffAccountForm.confirmPassword) {
      setError("The password and confirmation do not match.");
      return;
    }

    setStaffAccountSaving(true);
    try {
      const response = await api.post("/staff/users", {
        username: staffAccountForm.username,
        password: staffAccountForm.password,
        role: staffAccountForm.role,
      });
      setStaffAccountForm({
        username: "",
        password: "",
        confirmPassword: "",
        role: "support",
      });
      setStaffAccountMessage(response.data.message || "Staff account created.");
      await loadStaffUsers();
    } catch (requestError) {
      handleApiError(requestError, "Could not create the staff account.");
    } finally {
      setStaffAccountSaving(false);
    }
  }

  async function logout() {
    try {
      await api.post("/logout");
      sessionStorage.removeItem("staffAuthenticated");
      sessionStorage.removeItem("staffRole");
      sessionStorage.removeItem("staffUsername");
      navigate("/staff", { replace: true });
    } catch (requestError) {
      setError(messageFrom(requestError, "Could not securely end staff session."));
    }
  }

  function changeTab(nextTab) {
    setTab(nextTab);
    setError("");
    if (nextTab === "dashboard") loadDashboard();
    if (nextTab === "customers") {
      setCustomerQuery(customerSearch);
      loadCustomers(1, customerSearch);
    }
    if (nextTab === "transactions") {
      setTransactionForm({ ...initialTransactionForm, ...transactionFilters });
      loadTransactions(1, transactionFilters);
    }
    if (nextTab === "audit") {
      setAuditForm({ ...initialAuditForm, ...auditFilters });
      loadAudit(1, auditFilters);
    }
    if (nextTab === "staff") loadStaffUsers();
  }

  const canManageFlags = ["admin", "support"].includes(staff.role);
  const canManageStaff = staff.role === "admin";
  return (
    <main className="staff-page staff-operations-page">
      <header className="staff-header">
        <div className="staff-header-brand">
          <span className="staff-brand-mark" aria-hidden="true">B</span>
          <div className="staff-header-copy">
            <p className="eyebrow staff-eyebrow">BLUEBANK OPERATIONS</p>
            <h1>Staff operations</h1>
            <p className="muted staff-identity">
            Signed in as {staff.username} · {staff.role.replaceAll("_", " ")}
            </p>
            <nav className="staff-nav" aria-label="Staff pages">
              <button type="button" aria-current={tab === "dashboard" ? "page" : undefined} className={tab === "dashboard" ? "active" : ""} onClick={() => changeTab("dashboard")}>Overview</button>
              <button type="button" aria-current={tab === "customers" ? "page" : undefined} className={tab === "customers" ? "active" : ""} onClick={() => changeTab("customers")}>Customers</button>
              <button type="button" aria-current={tab === "transactions" ? "page" : undefined} className={tab === "transactions" ? "active" : ""} onClick={() => changeTab("transactions")}>Transactions</button>
              <button type="button" aria-current={tab === "audit" ? "page" : undefined} className={tab === "audit" ? "active" : ""} onClick={() => changeTab("audit")}>Audit log</button>
              {canManageStaff && <button type="button" aria-current={tab === "staff" ? "page" : undefined} className={tab === "staff" ? "active" : ""} onClick={() => changeTab("staff")}>Staff access</button>}
              <Link to="/staff/disputes">Disputes</Link>
            </nav>
          </div>
        </div>
        <button type="button" className="secondary-button staff-signout" onClick={logout}>
          Sign out
        </button>
      </header>

      {error && <p className="staff-error" role="alert">{error}</p>}

      {tab === "dashboard" && (
        <section className="panel staff-panel">
          <div className="staff-section-heading">
            <div>
              <p className="staff-section-kicker">WORK QUEUE</p>
              <h2>Operations overview</h2>
              <p className="staff-section-description">A current snapshot of dispute workload and account review activity.</p>
            </div>
          </div>
          {dashboardLoading && !summary ? (
            <p className="staff-loading" role="status">Loading operations summary...</p>
          ) : !summary ? (
            <p className="staff-empty">Operations summary is unavailable.</p>
          ) : (
            <>
              <div className="staff-metrics" aria-label="Operations summary">
                <article><span>Open disputes</span><strong>{summary.open_disputes}</strong></article>
                <article><span>Under review</span><strong>{summary.under_review_disputes}</strong></article>
                <article><span>Oldest active dispute</span><strong>{summary.oldest_dispute_hours}h</strong></article>
                <article><span>Active account flags</span><strong>{summary.active_account_flags}</strong></article>
                <article><span>Pending staff work</span><strong>{summary.pending_staff_work}</strong></article>
              </div>
              <div className="staff-subsection-heading">
                <div>
                  <h3>Recent flag activity</h3>
                  <p>Latest account review markers, including resolved items.</p>
                </div>
              </div>
              {recentFlags.length === 0 ? (
                <p className="staff-empty">No account flags have been recorded.</p>
              ) : (
                <div className="staff-flag-activity-list">
                  {recentFlags.map((flag) => (
                    <article className="staff-flag-activity" key={flag.id}>
                      <div className="staff-activity-topline">
                        <strong>{flag.account_number_masked}</strong>
                        <StatusBadge status={flag.status} />
                      </div>
                      <p>{flag.reason}</p>
                      <small>Recorded {formatDate(flag.created_at)}</small>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      )}

      {tab === "customers" && (
        <section className="panel staff-panel">
          <div className="staff-section-heading">
            <div>
              <p className="staff-section-kicker">CUSTOMER SUPPORT</p>
              <h2>Customer lookup</h2>
              <p className="staff-section-description">Find a customer to review recent activity and internal account flags.</p>
            </div>
            {!customersLoading && customerPage.total > 0 && (
              <span className="staff-result-count">{customerPage.total} customers</span>
            )}
          </div>
          <form
            className="staff-search-form"
            onSubmit={(event) => {
              event.preventDefault();
              setCustomerSearch(customerQuery.trim());
              loadCustomers(1, customerQuery.trim());
            }}
          >
            <label>
              Name, email, or account number
              <input
                value={customerQuery}
                maxLength={100}
                onChange={(event) => setCustomerQuery(event.target.value)}
                placeholder="Search customers"
              />
            </label>
            <button className="primary-button" disabled={customersLoading}>
              {customersLoading ? "Searching..." : "Search"}
            </button>
          </form>
          {customersLoading ? (
            <p className="staff-loading" role="status">Loading customer records...</p>
          ) : customers.length === 0 ? (
            <p className="staff-empty">No customers match this search.</p>
          ) : (
            <div className="staff-customer-list">
              {customers.map((customer) => (
                <article className="staff-customer" key={customer.account_ref}>
                  <button
                    type="button"
                    className="staff-customer-summary"
                    disabled={working}
                    onClick={() => openCustomer(customer)}
                    aria-expanded={selectedRef === customer.account_ref}
                  >
                    <span className="staff-customer-identity">
                      <strong>{customer.name}</strong>
                      <small>{customer.email_masked || "No email on file"}</small>
                    </span>
                    <span className="staff-customer-account">
                      <strong>{customer.account_number_masked}</strong>
                      <StatusBadge status={customer.status} />
                    </span>
                    <span className="staff-customer-flags">
                      <strong>{customer.active_flag_count}</strong>
                      <small>Active flags</small>
                    </span>
                    <span className="staff-customer-chevron" aria-hidden="true">
                      {selectedRef === customer.account_ref ? "−" : "+"}
                    </span>
                  </button>
                  <div className="staff-recent-transactions">
                    <div className="staff-subsection-heading">
                      <div>
                        <h3>Recent transactions</h3>
                        <p>Latest three account activities</p>
                      </div>
                    </div>
                    {customer.recent_transactions.length === 0 ? (
                      <p className="staff-inline-empty">No recent transactions.</p>
                    ) : customer.recent_transactions.map((transaction) => (
                      <article className="staff-mini-transaction" key={transaction.id}>
                        <div>
                          <strong>{String(transaction.type || "Transaction").replaceAll("_", " ")}</strong>
                          <small>{transaction.id}</small>
                        </div>
                        <strong>{formatAmount(transaction.amount)}</strong>
                        <StatusBadge status={transaction.status || "COMPLETED"} />
                        <small>{formatDate(transaction.created_at)}</small>
                      </article>
                    ))}
                  </div>
                  {selectedRef === customer.account_ref && (
                    <div className="staff-flag-panel">
                      <div className="staff-subsection-heading">
                        <div>
                          <h3>Account review flags</h3>
                          <p>Internal notes for support and review teams.</p>
                        </div>
                      </div>
                      {flags.length === 0 ? <p className="staff-inline-empty">No flags recorded.</p> : flags.map((flag) => (
                        <article className="staff-flag" key={flag.id}>
                          <div className="staff-flag-content">
                            <div className="staff-activity-topline">
                              <strong>{flag.id}</strong>
                              <StatusBadge status={flag.status} />
                            </div>
                            <p>{flag.reason}</p>
                            <small>Created by {flag.created_by || "Staff"} · {formatDate(flag.created_at)}</small>
                            {flag.resolution && <small>Resolution: {flag.resolution}</small>}
                          </div>
                          {flag.status === "ACTIVE" && canManageFlags && (
                            <div className="staff-flag-resolve">
                              <label>
                                Resolution
                                <input
                                  aria-label={`Resolution for flag ${flag.id}`}
                                  placeholder="Add a resolution note"
                                  value={resolutions[flag.id] || ""}
                                  maxLength={500}
                                  onChange={(event) => setResolutions((current) => ({
                                    ...current,
                                    [flag.id]: event.target.value,
                                  }))}
                                />
                              </label>
                              <button type="button" className="secondary-button" disabled={working || !resolutions[flag.id]?.trim()} onClick={() => resolveFlag(flag.id)}>Resolve flag</button>
                            </div>
                          )}
                        </article>
                      ))}
                      {canManageFlags && !flags.some((flag) => flag.status === "ACTIVE") && (
                        <form className="staff-flag-create" onSubmit={createFlag}>
                          <label>
                            Flag for review · reason required
                            <textarea
                              value={flagReason}
                              maxLength={500}
                              required
                              onChange={(event) => setFlagReason(event.target.value)}
                            />
                          </label>
                          <button className="primary-button" disabled={working || !flagReason.trim()}>Flag account</button>
                        </form>
                      )}
                      <p className="muted">Support flags are internal review markers and do not block customer activity.</p>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
          <Pagination data={customerPage} onChange={(page) => loadCustomers(page)} />
        </section>
      )}

      {tab === "staff" && canManageStaff && (
        <section className="panel staff-panel staff-access-panel">
          <div className="staff-section-heading">
            <div>
              <p className="staff-section-kicker">ACCESS CONTROL</p>
              <h2>Staff access</h2>
              <p className="staff-section-description">
                Create staff accounts and grant only the access needed for their work.
              </p>
            </div>
            {!staffUsersLoading && (
              <span className="staff-result-count">{staffUsers.length} accounts</span>
            )}
          </div>

          <div className="staff-role-guide" aria-label="Available staff roles">
            {staffRoleInfo.map((role) => (
              <article className="staff-role-card" key={role.value}>
                <strong>{role.label}</strong>
                <p>{role.access}</p>
              </article>
            ))}
          </div>

          <div className="staff-access-columns">
            <form className="staff-create-account" onSubmit={createStaffAccount}>
              <div>
                <h3>Create staff account</h3>
                <p>New accounts are stored securely with a hashed password.</p>
              </div>
              <label>
                Username
                <input
                  autoComplete="off"
                  minLength={3}
                  maxLength={32}
                  pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,31}"
                  value={staffAccountForm.username}
                  onChange={(event) => setStaffAccountForm({
                    ...staffAccountForm,
                    username: event.target.value,
                  })}
                  placeholder="e.g. support.jordan"
                  required
                />
                <small>3-32 letters, numbers, dots, underscores or hyphens.</small>
              </label>
              <label>
                Assign role
                <select
                  value={staffAccountForm.role}
                  onChange={(event) => setStaffAccountForm({
                    ...staffAccountForm,
                    role: event.target.value,
                  })}
                >
                  {staffRoleInfo.map((role) => (
                    <option key={role.value} value={role.value}>{role.label}</option>
                  ))}
                </select>
              </label>
              <label>
                Initial password
                <input
                  type="password"
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  value={staffAccountForm.password}
                  onChange={(event) => setStaffAccountForm({
                    ...staffAccountForm,
                    password: event.target.value,
                  })}
                  required
                />
                <small>At least 12 characters. Share it through an approved secure channel.</small>
              </label>
              <label>
                Confirm password
                <input
                  type="password"
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  value={staffAccountForm.confirmPassword}
                  onChange={(event) => setStaffAccountForm({
                    ...staffAccountForm,
                    confirmPassword: event.target.value,
                  })}
                  required
                />
              </label>
              {staffAccountMessage && <p className="staff-form-success" role="status">{staffAccountMessage}</p>}
              <button className="primary-button" disabled={staffAccountSaving}>
                {staffAccountSaving ? "Creating account..." : "Create staff account"}
              </button>
            </form>

            <section className="staff-account-directory" aria-labelledby="staff-directory-title">
              <div className="staff-directory-heading">
                <div>
                  <h3 id="staff-directory-title">Staff directory</h3>
                  <p>Reset passwords or control access. Passwords are never displayed.</p>
                </div>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={loadStaffUsers}
                  disabled={staffUsersLoading}
                >
                  Refresh
                </button>
              </div>
              {staffUsersLoading ? (
                <p className="staff-loading" role="status">Loading staff accounts...</p>
              ) : staffUsers.length === 0 ? (
                <p className="staff-empty">No staff accounts are configured.</p>
              ) : (
                <div className="staff-directory-list">
                  {staffUsers.map((user) => {
                    const role = staffRoleInfo.find((item) => item.value === user.role);
                    const isSelf = user.username.toLowerCase() === staff.username.toLowerCase();
                    const configurationMissing = user.source === "environment" && !user.source_configured;
                    return (
                      <article className="staff-directory-entry" key={user.id || `${user.source}-${user.username}`}>
                        <div className="staff-directory-main">
                          <div className="staff-directory-identity">
                            <strong>{user.username}</strong>
                            <small>{role?.label || user.role}{isSelf ? " · You" : ""}</small>
                          </div>
                          <div className="staff-directory-badges">
                            <span className={`staff-source-badge source-${user.source}`}>
                              {user.source === "environment" ? "Server config" : "Managed"}
                            </span>
                            <span className={`staff-account-state ${user.active ? "state-active" : "state-inactive"}`}>
                              {user.active ? "Active" : "Access revoked"}
                            </span>
                          </div>
                        </div>
                        <small className="staff-directory-meta">
                          {configurationMissing
                            ? "Removed from server configuration; sign-in is disabled."
                            : user.source === "environment"
                              ? "Credentials and role come from server configuration."
                              : `Created ${formatDate(user.created_at)}`}
                        </small>
                        {!configurationMissing && (
                          <div className="staff-directory-actions">
                            {user.active && (
                              <button
                                className="secondary-button"
                                type="button"
                                disabled={Boolean(staffActionSaving)}
                                onClick={() => {
                                  setStaffActionMessage("");
                                  setPasswordResetTarget(
                                    passwordResetTarget === user.id ? "" : user.id,
                                  );
                                  setPasswordResetForm({ password: "", confirmPassword: "" });
                                }}
                              >
                                {passwordResetTarget === user.id ? "Cancel reset" : "Reset password"}
                              </button>
                            )}
                            {user.active ? (
                              <button
                                className="danger-button"
                                type="button"
                                disabled={Boolean(staffActionSaving) || isSelf}
                                title={isSelf ? "You cannot revoke your own access." : undefined}
                                onClick={() => changeStaffAccess(user, "revoke")}
                              >
                                Revoke access
                              </button>
                            ) : (
                              <button
                                className="secondary-button"
                                type="button"
                                disabled={Boolean(staffActionSaving)}
                                onClick={() => changeStaffAccess(user, "reactivate")}
                              >
                                Reactivate
                              </button>
                            )}
                          </div>
                        )}
                        {passwordResetTarget === user.id && user.active && (
                          <form
                            className="staff-password-reset"
                            onSubmit={(event) => resetStaffPassword(event, user)}
                          >
                            <p>
                              Set a new password for <strong>{user.username}</strong>.
                              Existing sessions will be ended.
                            </p>
                            <label>
                              New password
                              <input
                                type="password"
                                autoComplete="new-password"
                                minLength={12}
                                maxLength={128}
                                value={passwordResetForm.password}
                                onChange={(event) => setPasswordResetForm({
                                  ...passwordResetForm,
                                  password: event.target.value,
                                })}
                                required
                              />
                            </label>
                            <label>
                              Confirm new password
                              <input
                                type="password"
                                autoComplete="new-password"
                                minLength={12}
                                maxLength={128}
                                value={passwordResetForm.confirmPassword}
                                onChange={(event) => setPasswordResetForm({
                                  ...passwordResetForm,
                                  confirmPassword: event.target.value,
                                })}
                                required
                              />
                            </label>
                            <button
                              className="primary-button"
                              type="submit"
                              disabled={Boolean(staffActionSaving)}
                            >
                              {staffActionSaving === user.id ? "Resetting..." : "Save new password"}
                            </button>
                          </form>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}
              {staffActionMessage && <p className="staff-form-success" role="status">{staffActionMessage}</p>}
            </section>
          </div>
        </section>
      )}

      {tab === "transactions" && (
        <section className="panel staff-panel">
          <div className="staff-section-heading">
            <div>
              <p className="staff-section-kicker">ACCOUNT ACTIVITY</p>
              <h2>Transaction search</h2>
              <p className="staff-section-description">Search-only view of customer transactions. Sensitive account numbers stay masked.</p>
            </div>
            {!transactionsLoading && transactionPage.total > 0 && (
              <span className="staff-result-count">{transactionPage.total} transactions</span>
            )}
          </div>
          <form
            className="staff-search-form staff-transaction-filters"
            onSubmit={(event) => {
              event.preventDefault();
              loadTransactions(1, transactionForm);
            }}
          >
            <label>Reference or transaction ID<input value={transactionForm.q} onChange={(event) => setTransactionForm({ ...transactionForm, q: event.target.value })} /></label>
            <label>Account number or last 4<input maxLength={11} value={transactionForm.account_number} onChange={(event) => setTransactionForm({ ...transactionForm, account_number: event.target.value })} /></label>
            <label>Type<select value={transactionForm.type} onChange={(event) => setTransactionForm({ ...transactionForm, type: event.target.value })}>
              <option value="">All types</option>
              <option value="DEPOSIT">Deposit</option>
              <option value="WITHDRAW">Withdrawal</option>
              <option value="TRANSFER">Transfer sent</option>
              <option value="TRANSFER_RECEIVED">Transfer received</option>
              <option value="CARD_PAYMENT">Card payment</option>
              <option value="SCHEDULED_TRANSFER">Scheduled transfer</option>
              <option value="SAVINGS_CONTRIBUTION">Savings contribution</option>
              <option value="SAVINGS_WITHDRAWAL">Savings withdrawal</option>
              <option value="TRANSFER_REVERSAL_CREDIT">Transfer reversal credit</option>
              <option value="TRANSFER_REVERSAL_DEBIT">Transfer reversal debit</option>
            </select></label>
            <label>Status<select value={transactionForm.status} onChange={(event) => setTransactionForm({ ...transactionForm, status: event.target.value })}>
              <option value="">All statuses</option>
              <option value="COMPLETED">Completed</option>
              <option value="PENDING">Pending</option>
              <option value="FAILED">Failed</option>
              <option value="REVERSED">Reversed</option>
              <option value="CANCELLED">Cancelled</option>
            </select></label>
            <label>From<input type="date" value={transactionForm.from} onChange={(event) => setTransactionForm({ ...transactionForm, from: event.target.value })} /></label>
            <label>To<input type="date" value={transactionForm.to} onChange={(event) => setTransactionForm({ ...transactionForm, to: event.target.value })} /></label>
            <label>Minimum amount<input type="number" min="0" step="0.01" value={transactionForm.min_amount} onChange={(event) => setTransactionForm({ ...transactionForm, min_amount: event.target.value })} /></label>
            <label>Maximum amount<input type="number" min="0" step="0.01" value={transactionForm.max_amount} onChange={(event) => setTransactionForm({ ...transactionForm, max_amount: event.target.value })} /></label>
            <button className="primary-button" disabled={transactionsLoading}>
              {transactionsLoading ? "Searching..." : "Search transactions"}
            </button>
          </form>
          {transactionsLoading ? (
            <p className="staff-loading" role="status">Searching transactions...</p>
          ) : transactions.length === 0 ? (
            <p className="staff-empty">No transactions match these filters.</p>
          ) : (
            <div className="staff-transaction-list">
              {transactions.map((transaction) => (
                <article className="staff-transaction-card" key={`${transaction.account_ref}-${transaction.id}`}>
                  <div className="staff-transaction-card-heading">
                    <div>
                      <p className="staff-card-kicker">TRANSACTION</p>
                      <h3>{String(transaction.type || "Transaction").replaceAll("_", " ")}</h3>
                    </div>
                    <div className="staff-transaction-amount">
                      <strong>{formatAmount(transaction.amount)}</strong>
                      <StatusBadge status={transaction.status} />
                    </div>
                  </div>
                  <dl className="staff-data-grid">
                    <div>
                      <dt>Account</dt>
                      <dd>{transaction.account_number_masked}</dd>
                    </div>
                    <div>
                      <dt>Transaction ID</dt>
                      <dd>{transaction.id || "Not available"}</dd>
                    </div>
                    <div>
                      <dt>Reference</dt>
                      <dd>{transaction.reference || "—"}</dd>
                    </div>
                    <div>
                      <dt>Date and time</dt>
                      <dd>{formatDate(transaction.created_at)}</dd>
                    </div>
                    {transaction.description && (
                      <div className="staff-data-wide">
                        <dt>Description</dt>
                        <dd>{transaction.description}</dd>
                      </div>
                    )}
                  </dl>
                </article>
              ))}
            </div>
          )}
          <Pagination data={transactionPage} onChange={(page) => loadTransactions(page)} />
        </section>
      )}

      {tab === "audit" && (
        <section className="panel staff-panel">
          <div className="staff-section-heading">
            <div>
              <p className="staff-section-kicker">ACCOUNTABILITY</p>
              <h2>Staff audit log</h2>
              <p className="staff-section-description">Review staff actions and access events recorded by the system.</p>
            </div>
            {!auditLoading && auditPage.total > 0 && (
              <span className="staff-result-count">{auditPage.total} events</span>
            )}
          </div>
          <form
            className="staff-search-form staff-audit-filters"
            onSubmit={(event) => {
              event.preventDefault();
              loadAudit(1, auditForm);
            }}
          >
            <label>Staff username<input value={auditForm.actor} onChange={(event) => setAuditForm({ ...auditForm, actor: event.target.value })} /></label>
            <label>Action<input value={auditForm.action} onChange={(event) => setAuditForm({ ...auditForm, action: event.target.value })} /></label>
            <label>Entity / reference<input value={auditForm.entity_id} onChange={(event) => setAuditForm({ ...auditForm, entity_id: event.target.value })} /></label>
            <label>From<input type="date" value={auditForm.from} onChange={(event) => setAuditForm({ ...auditForm, from: event.target.value })} /></label>
            <label>To<input type="date" value={auditForm.to} onChange={(event) => setAuditForm({ ...auditForm, to: event.target.value })} /></label>
            <button className="primary-button" disabled={auditLoading}>
              {auditLoading ? "Filtering..." : "Filter audit log"}
            </button>
          </form>
          {auditLoading ? (
            <p className="staff-loading" role="status">Loading audit events...</p>
          ) : auditEntries.length === 0 ? (
            <p className="staff-empty">No audit events match these filters.</p>
          ) : (
            <div className="staff-audit-list">
              {auditEntries.map((entry) => (
                <article className="staff-audit-card" key={entry.id}>
                  <div className="staff-audit-card-heading">
                    <div>
                      <p className="staff-card-kicker">STAFF ACTION</p>
                      <h3>{String(entry.action || "Activity").replaceAll("_", " ")}</h3>
                    </div>
                    <time>{formatDate(entry.created_at)}</time>
                  </div>
                  <dl className="staff-data-grid staff-audit-data">
                    <div>
                      <dt>Staff member</dt>
                      <dd>{entry.actor || "Not available"}</dd>
                    </div>
                    <div>
                      <dt>Entity / reference</dt>
                      <dd>{entry.entity_id || "Not available"}</dd>
                    </div>
                    {entry.details && (
                      <div className="staff-data-wide">
                        <dt>Details</dt>
                        <dd className="staff-audit-details">
                          {Object.entries(entry.details).map(([key, value]) => (
                            <span key={key}>
                              <strong>{key.replaceAll("_", " ")}</strong>
                              {typeof value === "object" && value !== null
                                ? JSON.stringify(value)
                                : String(value)}
                            </span>
                          ))}
                        </dd>
                      </div>
                    )}
                  </dl>
                </article>
              ))}
            </div>
          )}
          <Pagination data={auditPage} onChange={(page) => loadAudit(page)} />
        </section>
      )}
    </main>
  );
}

function Pagination({ data, onChange }) {
  if (!data.pages || data.pages < 2) return null;
  return (
    <div className="staff-pagination">
      <button type="button" className="secondary-button" disabled={data.page <= 1} onClick={() => onChange(data.page - 1)}>Previous</button>
      <span>Page {data.page} of {data.pages} · {data.total} results</span>
      <button type="button" className="secondary-button" disabled={data.page >= data.pages} onClick={() => onChange(data.page + 1)}>Next</button>
    </div>
  );
}
