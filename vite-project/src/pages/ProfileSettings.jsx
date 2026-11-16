import { useEffect, useState } from "react";
import api from "../services/api";
import { useToast } from "../components/Toast";

export default function ProfileSettings() {
  const [account, setAccount] = useState(null);
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [activeSection, setActiveSection] = useState("personal");

  const [securityActivity, setSecurityActivity] = useState([]);
  const [securityLoading, setSecurityLoading] = useState(false);
  const [twoFAEnabled, setTwoFAEnabled] = useState(false);
  const [twoFASetup, setTwoFASetup] = useState(null);
  const [twoFACode, setTwoFACode] = useState("");
  const [twoFALoading, setTwoFALoading] = useState(false);

  const { showToast } = useToast();

  async function loadSecurityActivity() {
    setSecurityLoading(true);

    try {
      const response = await api.get("/security/activity");

      setSecurityActivity(
        response.data.activities || []
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not load security activity.",
        "error"
      );
    } finally {
      setSecurityLoading(false);
    }
  }

  async function loadTwoFAStatus() {
  try {
    const response = await api.get("/2fa/status");
    setTwoFAEnabled(response.data.enabled);
  } catch (error) {
    showToast(
      error.response?.data?.message ||
        "Could not load two-factor authentication status.",
      "error"
    );
  }
}

async function startTwoFASetup() {
  setTwoFALoading(true);

  try {
    const response = await api.post("/2fa/setup");
    setTwoFASetup(response.data);
    setTwoFACode("");
  } catch (error) {
    showToast(
      error.response?.data?.message ||
        "Unable to start two-factor authentication setup.",
      "error"
    );
  } finally {
    setTwoFALoading(false);
  }
}

async function verifyTwoFASetup() {
  if (twoFACode.length !== 6) {
    showToast("Enter the 6-digit authenticator code.", "warning");
    return;
  }

  setTwoFALoading(true);

  try {
    await api.post("/2fa/verify-setup", {
      code: twoFACode,
    });

    setTwoFAEnabled(true);
    setTwoFASetup(null);
    setTwoFACode("");

    showToast(
      "Two-factor authentication enabled successfully.",
      "success"
    );

    loadSecurityActivity();
  } catch (error) {
    showToast(
      error.response?.data?.message ||
        "Invalid authenticator code.",
      "error"
    );
  } finally {
    setTwoFALoading(false);
  }
}

async function disableTwoFA() {
  if (twoFACode.length !== 6) {
    showToast(
      "Enter your current 6-digit authenticator code.",
      "warning"
    );
    return;
  }

  setTwoFALoading(true);

  try {
    await api.post("/2fa/disable", {
      code: twoFACode,
    });

    setTwoFAEnabled(false);
    setTwoFACode("");

    showToast(
      "Two-factor authentication disabled successfully.",
      "success"
    );

    loadSecurityActivity();
  } catch (error) {
    showToast(
      error.response?.data?.message ||
        "Unable to disable two-factor authentication.",
      "error"
    );
  } finally {
    setTwoFALoading(false);
  }
}

  useEffect(() => {
    async function loadProfile() {
      try {
        const response = await api.get("/account");

        const profile = response.data.account;

        setAccount(profile);
        setEmail(profile.email || "");

        sessionStorage.setItem(
          "bankAccount",
          JSON.stringify(profile)
        );
      } catch (error) {
        showToast(
          error.response?.data?.message ||
            "Could not load your profile.",
          "error"
        );
      } finally {
        setLoading(false);
      }
    }

    loadProfile();
  }, [showToast]);

  useEffect(() => {
    if (activeSection === "security") {
      loadSecurityActivity();
      loadTwoFAStatus();
    }
  }, [activeSection]);

  async function handleEmailUpdate(event) {
    event.preventDefault();

    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      showToast(
        "Email address is required.",
        "warning"
      );
      return;
    }

    setSaving(true);

    try {
      const response = await api.put("/profile", {
        email: trimmedEmail,
      });

      const updatedAccount = response.data.account;

      setAccount(updatedAccount);
      setEmail(updatedAccount.email || "");

      sessionStorage.setItem(
        "bankAccount",
        JSON.stringify(updatedAccount)
      );

      showToast(
        response.data.message ||
          "Email address updated successfully.",
        "success"
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not update your email address.",
        "error"
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div>
        <p className="eyebrow">PROFILE & SETTINGS</p>

        <h1>Profile & Settings</h1>

        <p className="muted">
          Loading your profile...
        </p>
      </div>
    );
  }

  if (!account) {
    return (
      <div className="notice error">
        Could not load your profile.
      </div>
    );
  }

  const menuItems = [
    {
      id: "personal",
      label: "Personal information",
    },
    {
      id: "contact",
      label: "Contact details",
    },
    {
      id: "account",
      label: "Account details",
    },
    {
      id: "kyc",
      label: "KYC information",
    },
    {
      id: "security",
      label: "Security",
    },
  ];

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            PROFILE & SETTINGS
          </p>

          <h1>Profile & Settings</h1>

          <p className="muted">
            Manage your personal information and banking
            preferences.
          </p>
        </div>
      </div>

      {/* Profile header */}

      <section className="panel profile-hero">
        <div className="profile-avatar">
          {(account.name || "U")
            .charAt(0)
            .toUpperCase()}
        </div>

        <div className="profile-hero-info">
          <h2>{account.name}</h2>

          <p>
            Personal Banking Customer
          </p>

          <span>
            Account ending in{" "}
            {account.account_number.slice(-4)}
          </span>
        </div>

        <div className="profile-active-status">
          <span></span>
          Active
        </div>
      </section>

      <div className="profile-page-layout">

        {/* Profile navigation */}

        <aside className="panel profile-menu">
          <div className="profile-menu-title">
            PROFILE
          </div>

          {menuItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={
                activeSection === item.id
                  ? "profile-menu-item active"
                  : "profile-menu-item"
              }
              onClick={() =>
                setActiveSection(item.id)
              }
            >
              <span>
                {item.id === "personal" && "◉"}
                {item.id === "contact" && "✉"}
                {item.id === "account" && "$"}
                {item.id === "kyc" && "✓"}
                {item.id === "security" && "⌑"}
              </span>

              {item.label}
            </button>
          ))}
        </aside>

        {/* Main profile content */}

        <main className="panel profile-content">

          {/* Personal */}

          {activeSection === "personal" && (
            <section>
              <div className="profile-content-heading">
                <div>
                  <h2>Personal information</h2>

                  <p>
                    Your basic personal information
                    registered with BlueBank.
                  </p>
                </div>

                <span className="verified-badge">
                  ✓ Verified
                </span>
              </div>

              <div className="profile-details-grid">

                <div className="profile-detail">
                  <span>Full name</span>
                  <strong>{account.name}</strong>
                </div>

                <div className="profile-detail">
                  <span>Age</span>
                  <strong>{account.age}</strong>
                </div>

                <div className="profile-detail">
                  <span>Customer ID</span>

                  <strong>
                    BB-
                    {account.account_number.slice(-6)}
                  </strong>
                </div>

                <div className="profile-detail">
                  <span>Customer type</span>
                  <strong>
                    Personal Banking
                  </strong>
                </div>

              </div>

              <div className="profile-info-note">
                <span>i</span>

                <p>
                  Personal information is maintained
                  by the bank and cannot be changed
                  from this page.
                </p>
              </div>
            </section>
          )}

          {/* Contact */}

          {activeSection === "contact" && (
            <section>
              <div className="profile-content-heading">
                <div>
                  <h2>Contact details</h2>

                  <p>
                    Manage the contact information
                    associated with your account.
                  </p>
                </div>
              </div>

              <div className="contact-card">
                <div className="contact-card-icon">
                  @
                </div>

                <div className="contact-card-content">
                  <span>
                    Registered email address
                  </span>

                  <strong>
                    {account.email || "Not added"}
                  </strong>

                  <small>
                    Used for account notifications
                    and communication.
                  </small>
                </div>

                <span
                  className={
                    account.email
                      ? "verified-badge"
                      : "pending-badge"
                  }
                >
                  {account.email
                    ? "✓ Added"
                    : "Not added"}
                </span>
              </div>

              <form
                className="profile-update-form"
                onSubmit={handleEmailUpdate}
              >
                <label htmlFor="profile-email">
                  Email address
                </label>

                <div className="profile-input-row">
                  <input
                    id="profile-email"
                    type="email"
                    value={email}
                    placeholder="you@example.com"
                    onChange={(event) =>
                      setEmail(event.target.value)
                    }
                    autoComplete="email"
                  />

                  <button
                    type="submit"
                    className="primary-button"
                    disabled={saving}
                  >
                    {saving
                      ? "Saving..."
                      : account.email
                      ? "Update email"
                      : "Add email"}
                  </button>
                </div>
              </form>

              <div className="profile-info-note">
                <span>i</span>

                <p>
                  Email changes may require
                  verification before becoming the
                  primary communication address.
                </p>
              </div>
            </section>
          )}

          {/* Account */}

          {activeSection === "account" && (
            <section>
              <div className="profile-content-heading">
                <div>
                  <h2>Account details</h2>

                  <p>
                    Information about your BlueBank
                    account.
                  </p>
                </div>
              </div>

              <div className="profile-details-grid">

                <div className="profile-detail">
                  <span>Account number</span>

                  <strong>
                    •••••••
                    {account.account_number.slice(-4)}
                  </strong>
                </div>

                <div className="profile-detail">
                  <span>Account type</span>

                  <strong>
                    Personal Savings
                  </strong>
                </div>

                <div className="profile-detail">
                  <span>Account status</span>

                  <strong className="text-success">
                    Active
                  </strong>
                </div>

                <div className="profile-detail">
                  <span>Available balance</span>

                  <strong>
                    $
                    {Number(
                      account.balance
                    ).toFixed(2)}
                  </strong>
                </div>

              </div>
            </section>
          )}

          {/* KYC */}

          {activeSection === "kyc" && (
            <section>
              <div className="profile-content-heading">
                <div>
                  <h2>KYC information</h2>

                  <p>
                    Your identity and regulatory
                    information.
                  </p>
                </div>
              </div>

              <div className="kyc-status-card">
                <div className="kyc-check">
                  ✓
                </div>

                <div>
                  <strong>KYC status</strong>

                  <p>
                    Your account is currently active.
                  </p>
                </div>

                <span className="verified-badge">
                  Verified
                </span>
              </div>

              <div className="profile-details-grid">

                <div className="profile-detail">
                  <span>PAN</span>
                  <strong>Not added</strong>
                </div>

                <div className="profile-detail">
                  <span>Aadhaar</span>
                  <strong>Not added</strong>
                </div>

                <div className="profile-detail">
                  <span>Occupation</span>
                  <strong>Not added</strong>
                </div>

                <div className="profile-detail">
                  <span>Annual income</span>
                  <strong>Not added</strong>
                </div>

              </div>

              <div className="profile-info-note">
                <span>i</span>

                <p>
                  KYC fields will become editable
                  when the corresponding banking
                  services are implemented.
                </p>
              </div>
            </section>
          )}

          {/* Security */}

          {activeSection === "security" && (
            <section>
              <div className="profile-content-heading">
                <div>
                  <h2>Security</h2>

                  <p>
                    Manage your account security
                    settings and review recent activity.
                  </p>
                </div>
              </div>

              <div className="security-option">
                <div>
                  <strong>Login PIN</strong>

                  <p>
                    Your PIN is protected and never
                    displayed.
                  </p>
                </div>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    window.location.href =
                      "/change-pin";
                  }}
                >
                  Change PIN
                </button>
              </div>

              <div className="security-option">
                <div>
                  <strong>
                    Account protection
                  </strong>

                  <p>
                    Your account is protected with
                    secure authentication.
                  </p>
                </div>

                <span className="verified-badge">
                  Protected
                </span>
              </div>
              
              <div className="security-option">
              <div>
                <strong>Two-Factor Authentication</strong>

                <p>
                  Protect your account with Google Authenticator.
                </p>
              </div>

              <div className="two-fa-actions">
              <span
                className={
                  twoFAEnabled
                    ? "verified-badge"
                    : "pending-badge"
                }
              >
                {twoFAEnabled ? "Enabled" : "Disabled"}
              </span>

              {!twoFAEnabled && !twoFASetup && (
                <button
                  type="button"
                  className="security-action-button"
                  onClick={startTwoFASetup}
                  disabled={twoFALoading}
                >
                  {twoFALoading ? "Preparing..." : "Enable"}
                </button>
              )}
            </div>
            </div>

            {/* {twoFASetup && (
              <div className="two-fa-setup">
                <h3>Set up Google Authenticator</h3>

                <p className="muted">
                  Scan the QR code using the Google Authenticator app.
                </p>

                <img
                  src={twoFASetup.qr_code}
                  alt="Google Authenticator QR code"
                  className="two-fa-qr"
                />

                <p className="muted">
                  Can't scan? Use this setup key:
                </p>

                <code className="two-fa-secret">
                  {twoFASetup.secret}
                </code>

                <label htmlFor="twoFACode">
                  Verification code
                </label>

                <input
                  id="twoFACode"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  placeholder="Enter 6-digit code"
                  value={twoFACode}
                  onChange={(event) =>
                    setTwoFACode(
                      event.target.value.replace(/\D/g, "")
                    )
                  }
                />

                <button
                  type="button"
                  className="primary-button"
                  onClick={verifyTwoFASetup}
                  disabled={
                    twoFALoading ||
                    twoFACode.length !== 6
                  }
                >
                  {twoFALoading
                    ? "Verifying..."
                    : "Verify & Enable"}
                </button>
              </div>
            )} */}

            {/* {twoFAEnabled && (
              <div className="two-fa-disable">
                <p className="muted">
                  Google Authenticator is currently protecting
                  your account.
                </p>

                <label htmlFor="disableTwoFACode">
                  Enter your current authenticator code to disable 2FA
                </label>

                <input
                  id="disableTwoFACode"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  placeholder="Enter 6-digit code"
                  value={twoFACode}
                  onChange={(event) =>
                    setTwoFACode(
                      event.target.value.replace(/\D/g, "")
                    )
                  }
                />

                <button
                  type="button"
                  className="secondary-button"
                  onClick={disableTwoFA}
                  disabled={
                    twoFALoading ||
                    twoFACode.length !== 6
                  }
                >
                  {twoFALoading
                    ? "Disabling..."
                    : "Disable 2FA"}
                </button>
              </div>
            )} */}

            {/* {!twoFAEnabled && !twoFASetup && (
              <div className="two-fa-action">
                <button
                  type="button"
                  className="primary-button"
                  onClick={startTwoFASetup}
                  disabled={twoFALoading}
                >
                  {twoFALoading
                    ? "Preparing..."
                    : "Enable Google Authenticator"}
                </button>
              </div>
            )} */}

            {twoFASetup && (
              <div className="two-fa-setup">
                <h3>Set up Google Authenticator</h3>

                <p className="muted">
                  Scan this QR code using the Google Authenticator app.
                </p>

                <img
                  src={twoFASetup.qr_code}
                  alt="Google Authenticator QR code"
                  className="two-fa-qr"
                />

                <p className="muted">
                  Can't scan the QR code? Use this setup key:
                </p>

                <code className="two-fa-secret">
                  {twoFASetup.secret}
                </code>

                <label htmlFor="twoFACode">
                  Verification code
                </label>

                <input
                  id="twoFACode"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  placeholder="Enter 6-digit code"
                  value={twoFACode}
                  onChange={(event) =>
                    setTwoFACode(
                      event.target.value.replace(/\D/g, "")
                    )
                  }
                />

                <button
                  type="button"
                  className="primary-button"
                  onClick={verifyTwoFASetup}
                  disabled={
                    twoFALoading ||
                    twoFACode.length !== 6
                  }
                >
                  {twoFALoading
                    ? "Verifying..."
                    : "Verify & Enable"}
                </button>
              </div>
            )}

            {twoFAEnabled && (
              <div className="two-fa-disable">
                <p className="muted">
                  Google Authenticator is currently protecting
                  your account.
                </p>

                <label htmlFor="disableTwoFACode">
                  Enter your current authenticator code
                </label>

                <input
                  id="disableTwoFACode"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  placeholder="Enter 6-digit code"
                  value={twoFACode}
                  onChange={(event) =>
                    setTwoFACode(
                      event.target.value.replace(/\D/g, "")
                    )
                  }
                />

                <button
                  type="button"
                  className="secondary-button"
                  onClick={disableTwoFA}
                  disabled={
                    twoFALoading ||
                    twoFACode.length !== 6
                  }
                >
                  {twoFALoading
                    ? "Disabling..."
                    : "Disable 2FA"}
                </button>
              </div>
            )}

              {/* Recent login activity */}

              <div
                className="profile-section-heading"
                style={{ marginTop: "24px" }}
              >
                <div>
                  <h3>
                    Recent login activity
                  </h3>

                  <p>
                    Review recent access to your
                    BlueBank account.
                  </p>
                </div>
              </div>

              <div className="security-activity-list">
                {securityLoading ? (
                  <p className="muted">
                    Loading security activity...
                  </p>
                ) : securityActivity.length === 0 ? (
                  <div className="profile-info-note">
                    <span>i</span>

                    <p>
                      No security activity has been
                      recorded yet.
                    </p>
                  </div>
                ) : (
                  securityActivity.map((item) => {
                    const date = new Date(
                      item.created_at
                    );

                    const successful =
                      item.status === "SUCCESS";

                    return (
                      <div
                        className="security-activity-item"
                        key={item.id}
                      >
                        <div
                          className={`security-activity-icon ${
                            successful
                              ? "success"
                              : "failed"
                          }`}
                        >
                          {successful
                            ? "✓"
                            : "!"}
                        </div>

                        <div className="security-activity-info">
                          <strong>
                            {item.event}{" "}
                            {successful
                              ? "successful"
                              : "failed"}
                          </strong>

                          <span>
                            {item.device}{" "}
                            •{" "}
                            {item.browser}
                          </span>

                          <small>
                            {date.toLocaleDateString()}{" "}
                            {date.toLocaleTimeString()}
                          </small>
                        </div>

                        <span
                          className={
                            successful
                              ? "verified-badge"
                              : "pending-badge"
                          }
                        >
                          {successful
                            ? "Successful"
                            : "Failed"}
                        </span>
                      </div>
                    );
                  })
                )}
              </div>
            </section>
          )}

        </main>
      </div>
    </>
  );
}