import { useEffect, useState } from "react";
import api from "../services/api";

export default function AccountDetails() {
  const [account, setAccount] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/account")
      .then((response) => setAccount(response.data.account))
      .catch((err) => setError(err.response?.data?.message || "Unable to load account details."));
  }, []);

  if (error) return <div className="notice error">{error}</div>;
  if (!account) return <p className="muted">Loading account details...</p>;

  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">PROFILE</p><h1>Account details</h1><p className="muted">Your personal and banking information.</p></div></div>
      <section className="panel details-panel">
        <div className="profile-heading"><div className="profile-avatar">{account.name.charAt(0).toUpperCase()}</div><div><h2>{account.name}</h2><p>Bank account holder</p></div></div>
        <div className="details-list">
          <div><span>Full name</span><strong>{account.name}</strong></div>
          <div><span>Age</span><strong>{account.age} years</strong></div>
          <div><span>Account number</span><strong>{account.account_number}</strong></div>
          <div><span>Available balance</span><strong>${Number(account.balance).toFixed(2)}</strong></div>
          <div><span>PIN</span><strong>•••• (protected)</strong></div>
        </div>
      </section>
    </>
  );
}
