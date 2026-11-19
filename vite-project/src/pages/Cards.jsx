import { useEffect, useState } from "react";
import api from "../services/api";
import { useToast } from "../components/useToast";
import ConfirmModal from "../components/ConfirmModal";

const initialPaymentForm = {
  merchant: "",
  category: "Shopping",
  amount: "",
  pin: "",
};

export default function Cards() {
  const [cards, setCards] = useState([]);
  const [virtualCards, setVirtualCards] = useState([]);
  const [loading, setLoading] = useState(true);

  const [issuing, setIssuing] = useState(false);
  const [activating, setActivating] = useState(null);
  const [updatingStatus, setUpdatingStatus] = useState(null);

  const [editingLimit, setEditingLimit] = useState(null);
  const [newLimit, setNewLimit] = useState("");
  const [updatingLimit, setUpdatingLimit] = useState(false);

  const [paymentCard, setPaymentCard] = useState(null);

  const [paymentForm, setPaymentForm] = useState(initialPaymentForm);

  const [paying, setPaying] = useState(false);

  const [transactions, setTransactions] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [activeActivityCardId, setActiveActivityCardId] =
    useState(null);

  const [virtualIssuing, setVirtualIssuing] =
    useState(false);

  const [confirmAction, setConfirmAction] =
    useState(null);

  const { showToast } = useToast();

  async function loadCards() {
    try {
      const response = await api.get("/cards");

      setCards(response.data.cards || []);
      setVirtualCards(
        response.data.virtual_cards || []
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not load your cards.",
        "error"
      );
    } finally {
      setLoading(false);
    }
  }

  function closeActivity() {
    setTransactions([]);
    setAnalytics(null);
    setActiveActivityCardId(null);
  }

  function closePaymentForm() {
    setPaymentCard(null);
    setPaymentForm({ ...initialPaymentForm });
  }

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const response = await api.get("/cards");
        if (active) {
          setCards(response.data.cards || []);
          setVirtualCards(response.data.virtual_cards || []);
        }
      } catch (error) {
        if (active) {
          showToast(
            error.response?.data?.message || "Could not load your cards.",
            "error"
          );
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

  async function handleIssueCard() {
    setIssuing(true);

    try {
      const response = await api.post("/cards");

      setCards((prev) => [
        ...prev,
        response.data.card,
      ]);

      showToast(
        response.data.message,
        "success"
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not issue your card.",
        "error"
      );
    } finally {
      setIssuing(false);
    }
  }

  async function handleActivate(card) {
    setActivating(card.id);

    try {
      const response = await api.patch(
        `/cards/${card.id}/activate`
      );

      setCards((prev) =>
        prev.map((item) =>
          item.id === card.id
            ? response.data.card
            : item
        )
      );

      showToast(
        response.data.message,
        "success"
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not activate card.",
        "error"
      );
    } finally {
      setActivating(null);
    }
  }

  async function handleCardStatus(card) {
    const isFrozen =
      card.status === "FROZEN";

    setUpdatingStatus(card.id);

    try {
      const response = await api.patch(
        `/cards/${card.id}/${
          isFrozen
            ? "unfreeze"
            : "freeze"
        }`
      );

      setCards((prev) =>
        prev.map((item) =>
          item.id === card.id
            ? response.data.card
            : item
        )
      );

      showToast(
        response.data.message,
        "success"
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not update card status.",
        "error"
      );
    } finally {
      setUpdatingStatus(null);
    }
  }

  async function handleBlock(card) {
    setUpdatingStatus(card.id);

    try {
      const response = await api.patch(
        `/cards/${card.id}/block`
      );

      setCards((prev) =>
        prev.map((item) =>
          item.id === card.id
            ? response.data.card
            : item
        )
      );

      showToast(
        response.data.message,
        "success"
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not block card.",
        "error"
      );
    } finally {
      setUpdatingStatus(null);
      setConfirmAction(null);
    }
  }

  async function handleReplace(card) {
    setUpdatingStatus(card.id);

    try {
      const response = await api.post(
        `/cards/${card.id}/replace`
      );

      setCards((prev) =>
        prev
          .map((item) =>
            item.id === card.id
              ? response.data.old_card
              : item
          )
          .concat(response.data.card)
      );

      showToast(
        response.data.message,
        "success"
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not replace card.",
        "error"
      );
    } finally {
      setUpdatingStatus(null);
      setConfirmAction(null);
    }
  }

  async function handleUpdateLimit(card) {
    const amount = Number(newLimit);

    if (!Number.isFinite(amount)) {
      showToast(
        "Enter a valid daily limit.",
        "warning"
      );
      return;
    }

    if (amount < 100) {
      showToast(
        "Daily limit must be at least $100.",
        "warning"
      );
      return;
    }

    if (amount > 10000) {
      showToast(
        "Daily limit cannot exceed $10,000.",
        "warning"
      );
      return;
    }

    setUpdatingLimit(true);

    try {
      const response = await api.patch(
        `/cards/${card.id}/limit`,
        {
          daily_limit: newLimit,
        }
      );

      setCards((prev) =>
        prev.map((item) =>
          item.id === card.id
            ? response.data.card
            : item
        )
      );

      setEditingLimit(null);
      setNewLimit("");

      showToast(
        response.data.message,
        "success"
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not update card limit.",
        "error"
      );
    } finally {
      setUpdatingLimit(false);
    }
  }

  async function loadCardData(card) {
    try {
      const [
        transactionResponse,
        analyticsResponse,
      ] = await Promise.all([
        api.get(
          `/cards/${card.id}/transactions`
        ),
        api.get(
          `/cards/${card.id}/analytics`
        ),
      ]);

      setTransactions(
        transactionResponse.data.transactions ||
          []
      );

      setAnalytics(
        analyticsResponse.data
      );

      setActiveActivityCardId(card.id);
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not load card activity.",
        "error"
      );
    }
  }

  async function handlePaymentSubmit(event) {
    event.preventDefault();

    if (!paymentCard) return;

    setPaying(true);

    try {
      const response = await api.post(
        `/cards/${paymentCard.id}/payment`,
        paymentForm
      );

      closePaymentForm();

      closeActivity();

      showToast(
        response.data.message,
        "success"
      );

      await loadCards();
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Card payment failed.",
        "error"
      );
    } finally {
      setPaying(false);
    }
  }

  async function handleCreateVirtualCard() {
    setVirtualIssuing(true);

    try {
      const response = await api.post(
        "/cards/virtual"
      );

      setVirtualCards((prev) => [
        ...prev,
        response.data.card,
      ]);

      showToast(
        response.data.message,
        "success"
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not create virtual card.",
        "error"
      );
    } finally {
      setVirtualIssuing(false);
    }
  }

  function getAccountName() {
    const account = JSON.parse(
      sessionStorage.getItem(
        "bankAccount"
      ) || "{}"
    );

    return (
      account.name?.toUpperCase() ||
      "ACCOUNT HOLDER"
    );
  }

  if (loading) {
    return (
      <p className="muted">
        Loading your cards...
      </p>
    );
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            CARDS
          </p>

          <h1>My cards</h1>

          <p className="muted">
            Manage your physical and virtual
            BlueBank cards.
          </p>
        </div>
      </div>

      {/* =========================
          PHYSICAL CARDS
      ========================= */}

      <div className="section-title">
        <div>
          <h2>Debit cards</h2>

          <p>
            Manage your BlueBank debit cards.
          </p>
        </div>
      </div>

      {cards.length === 0 ? (
        <section className="panel card-empty-state">
          <div className="card-empty-icon">
            ▣
          </div>

          <h2>No debit card yet</h2>

          <p>
            Issue your BlueBank debit card to
            start making card payments.
          </p>

          <button
            className="primary-button"
            onClick={handleIssueCard}
            disabled={issuing}
          >
            {issuing
              ? "Issuing card..."
              : "Issue debit card"}
          </button>
        </section>
      ) : (
        <div className="cards-page">
          {cards.map((card) => (
            <section
              className="bank-card-section"
              key={card.id}
            >
              {/* =========================
                  CARD
              ========================= */}

              <div
                className={`bank-card ${
                  card.status.toLowerCase()
                }`}
              >
                <div className="bank-card-top">
                  <div className="bank-card-brand">
                    <span className="brand-mark small">
                      B
                    </span>

                    <span>
                      BlueBank
                    </span>
                  </div>

                  <span className="card-type">
                    {card.card_type}
                  </span>
                </div>

                <div className="card-chip">
                  ▦
                </div>

                <div className="card-number">
                  {card.masked_number}
                </div>

                <div className="bank-card-bottom">
                  <div>
                    <small>
                      CARD HOLDER
                    </small>

                    <strong>
                      {getAccountName()}
                    </strong>
                  </div>

                  <div>
                    <small>
                      VALID THRU
                    </small>

                    <strong>
                      {card.expiry}
                    </strong>
                  </div>

                  <div>
                    <small>
                      STATUS
                    </small>

                    <strong>
                      {card.status}
                    </strong>
                  </div>
                </div>
              </div>

              {/* =========================
                  CARD DETAILS
              ========================= */}

              <div className="card-details-panel">
                <div>
                  <span>
                    Card type
                  </span>

                  <strong>
                    {card.card_type}
                  </strong>
                </div>

                <div>
                  <span>
                    Last four digits
                  </span>

                  <strong>
                    {card.last_four}
                  </strong>
                </div>

                <div>
                  <span>
                    Daily spending limit
                  </span>

                  <strong>
                    $
                    {Number(
                      card.daily_limit
                    ).toFixed(2)}
                  </strong>
                </div>

                <div>
                  <span>
                    Card status
                  </span>

                  <strong
                    className={
                      card.status ===
                      "ACTIVE"
                        ? "text-success"
                        : card.status ===
                          "FROZEN"
                        ? "debit-text"
                        : ""
                    }
                  >
                    {card.status}
                  </strong>
                </div>
              </div>

              {/* =========================
                  CARD ACTIONS
              ========================= */}

              <div className="card-actions">
                {card.status ===
                  "ISSUED" && (
                  <button
                    className="primary-button"
                    onClick={() =>
                      handleActivate(
                        card
                      )
                    }
                    disabled={
                      activating ===
                      card.id
                    }
                  >
                    {activating ===
                    card.id
                      ? "Activating..."
                      : "Activate card"}
                  </button>
                )}

                {(card.status ===
                  "ACTIVE" ||
                  card.status ===
                    "FROZEN") && (
                  <button
                    className="secondary-button"
                    onClick={() => {
                      closeActivity();
                      handleCardStatus(
                        card
                      );
                    }}
                    disabled={
                      updatingStatus ===
                      card.id
                    }
                  >
                    {card.status ===
                    "FROZEN"
                      ? "Unfreeze card"
                      : "Freeze card"}
                  </button>
                )}

                {card.status !==
                  "BLOCKED" &&
                  card.status !==
                    "REPLACED" &&
                  card.status !==
                    "EXPIRED" && (
                    <>
                      <button
                        className="secondary-button"
                        onClick={() => {
                          closeActivity();
                          closePaymentForm();

                          setEditingLimit(
                            card.id
                          );

                          setNewLimit(
                            card.daily_limit
                          );
                        }}
                      >
                        Card settings
                      </button>

                      <button
                        className="secondary-button"
                        onClick={() => {
                          closePaymentForm();
                          setEditingLimit(
                            null
                          );

                          setConfirmAction(
                            null
                          );

                          loadCardData(
                            card
                          );
                        }}
                      >
                        Activity
                      </button>

                      <button
                        className="secondary-button"
                        onClick={() => {
                          closeActivity();
                          closePaymentForm();
                          setPaymentCard(
                            card
                          );
                        }}
                      >
                        Make payment
                      </button>

                      <button
                        className="danger-outline-button"
                        onClick={() => {
                          closeActivity();
                          closePaymentForm();

                          setConfirmAction({
                            type: "block",
                            card,
                          });
                        }}
                      >
                        Block card
                      </button>
                    </>
                  )}

                {(card.status ===
                  "ACTIVE" ||
                  card.status ===
                    "FROZEN" ||
                  card.status ===
                    "EXPIRED") && (
                  <button
                    className="secondary-button"
                    onClick={() => {
                      closeActivity();
                      closePaymentForm();

                      setConfirmAction({
                        type: "replace",
                        card,
                      });
                    }}
                  >
                    Replace card
                  </button>
                )}
              </div>

              {/* =========================
                  DAILY LIMIT
              ========================= */}

              {editingLimit ===
                card.id && (
                <div className="card-limit-editor">
                  <div>
                    <strong>
                      Daily spending limit
                    </strong>

                    <p>
                      Set a limit between
                      $100 and $10,000.
                    </p>
                  </div>

                  <div className="card-limit-form">
                    <div className="amount-input">
                      <span>
                        $
                      </span>

                      <input
                        type="number"
                        min="100"
                        max="10000"
                        step="0.01"
                        value={
                          newLimit
                        }
                        onChange={(e) =>
                          setNewLimit(
                            e.target.value
                          )
                        }
                      />
                    </div>

                    <button
                      className="primary-button"
                      onClick={() =>
                        handleUpdateLimit(
                          card
                        )
                      }
                      disabled={
                        updatingLimit
                      }
                    >
                      {updatingLimit
                        ? "Updating..."
                        : "Update limit"}
                    </button>

                    <button
                      className="secondary-button"
                      onClick={() => {
                        closeActivity();

                        setEditingLimit(
                          null
                        );

                        setNewLimit(
                          ""
                        );
                      }}
                      disabled={
                        updatingLimit
                      }
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* =========================
                  CARD ACTIVITY
              ========================= */}

              {activeActivityCardId ===
                card.id &&
                transactions.length >
                  0 && (
                  <div
                    className="card-transactions"
                    style={{
                      gridColumn:
                        "1 / -1",
                      width:
                        "100%",
                      minWidth:
                        0,
                      maxWidth:
                        "100%",
                      overflow:
                        "hidden",
                    }}
                  >
                    <div className="section-title">
                      <div>
                        <h2>
                          Card activity
                        </h2>

                        <p>
                          Recent payments made
                          with this card.
                        </p>
                      </div>
                    </div>

                    <div
                      className="panel"
                      style={{
                        width:
                          "100%",
                        maxWidth:
                          "100%",
                        minWidth:
                          0,
                        boxSizing:
                          "border-box",
                        overflow:
                          "hidden",
                      }}
                    >
                      <div
                        style={{
                          width:
                            "100%",
                          maxWidth:
                            "100%",
                          minWidth:
                            0,
                          overflow:
                            "hidden",
                        }}
                      >
                        <table
                          className="transaction-table"
                          style={{
                            width:
                              "100%",
                            maxWidth:
                              "100%",
                            minWidth:
                              0,
                            tableLayout:
                              "fixed",
                            borderCollapse:
                              "collapse",
                          }}
                        >
                          <thead>
                            <tr>
                              <th>
                                MERCHANT
                              </th>

                              <th>
                                CATEGORY
                              </th>

                              <th>
                                DATE
                              </th>

                              <th>
                                AMOUNT
                              </th>

                              <th>
                                STATUS
                              </th>
                            </tr>
                          </thead>

                          <tbody>
                            {transactions.map(
                              (
                                transaction
                              ) => (
                                <tr
                                  key={
                                    transaction.id
                                  }
                                >
                                  <td>
                                    <strong>
                                      {
                                        transaction.merchant
                                      }
                                    </strong>
                                  </td>

                                  <td>
                                    {
                                      transaction.category
                                    }
                                  </td>

                                  <td
                                    style={{
                                      whiteSpace:
                                        "nowrap",
                                    }}
                                  >
                                    {new Date(
                                      transaction.created_at
                                    ).toLocaleString()}
                                  </td>

                                  <td
                                    style={{
                                      whiteSpace:
                                        "nowrap",
                                      textAlign:
                                        "right",
                                    }}
                                  >
                                    <strong className="debit-text">
                                      −$
                                      {Number(
                                        transaction.amount
                                      ).toFixed(
                                        2
                                      )}
                                    </strong>
                                  </td>

                                  <td>
                                    {
                                      transaction.status
                                    }
                                  </td>
                                </tr>
                              )
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}
            </section>
          ))}
        </div>
      )}

      {/* =========================
          VIRTUAL CARD
      ========================= */}

      <div className="section-title">
        <div>
          <h2>
            Virtual card
          </h2>

          <p>
            Use a virtual card for online
            payments.
          </p>
        </div>
      </div>

      {virtualCards.length === 0 ? (
        <section className="panel virtual-card-empty">
          <div>
            <strong>
              No virtual card
            </strong>

            <p>
              Create a virtual card for
              online purchases.
            </p>
          </div>

          <button
            className="primary-button"
            onClick={
              handleCreateVirtualCard
            }
            disabled={
              virtualIssuing
            }
          >
            {virtualIssuing
              ? "Creating..."
              : "Create virtual card"}
          </button>
        </section>
      ) : (
        <div className="virtual-card-grid">
          {virtualCards.map(
            (card) => (
              <div
                className="virtual-bank-card"
                key={card.id}
              >
                <div className="bank-card-top">
                  <div className="bank-card-brand">
                    <span className="brand-mark small">
                      B
                    </span>

                    <span>
                      BlueBank
                    </span>
                  </div>

                  <span className="card-type">
                    VIRTUAL
                  </span>
                </div>

                <div className="card-number">
                  {
                    card.masked_number
                  }
                </div>

                <div className="bank-card-bottom">
                  <div>
                    <small>
                      CARD HOLDER
                    </small>

                    <strong>
                      {getAccountName()}
                    </strong>
                  </div>

                  <div>
                    <small>
                      VALID THRU
                    </small>

                    <strong>
                      {card.expiry}
                    </strong>
                  </div>

                  <div>
                    <small>
                      STATUS
                    </small>

                    <strong>
                      {card.status}
                    </strong>
                  </div>
                </div>
              </div>
            )
          )}
        </div>
      )}

      {/* =========================
          SPENDING ANALYTICS
      ========================= */}

      {analytics && (
        <section className="card-analytics">
          <div className="section-title">
            <div>
              <h2>
                Spending overview
              </h2>

              <p>
                Card spending by category.
              </p>
            </div>
          </div>

          <div className="card-analytics-grid">
            <div className="panel analytics-total">
              <span>
                Total card spending
              </span>

              <strong>
                $
                {Number(
                  analytics.total_spending
                ).toFixed(2)}
              </strong>
            </div>

            <div className="panel analytics-categories">
              {analytics.categories.length === 0 ? (
                <p className="muted">
                  No spending data yet.
                </p>
              ) : (
                analytics.categories.map((item) => {
                  const total = analytics.categories.reduce(
                    (sum, category) =>
                      sum + Number(category.amount),
                    0
                  );

                  const percentage =
                    total > 0
                      ? (Number(item.amount) / total) * 100
                      : 0;

                  return (
                    <div
                      className="analytics-row"
                      key={item.category}
                      style={{
                        "--category-percentage": `${percentage}%`,
                      }}
                    >
                      <span>
                        {item.category}
                      </span>

                      <strong>
                        $
                        {Number(item.amount).toFixed(2)}
                      </strong>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </section>
      )}

      {/* =========================
          PAYMENT FORM
      ========================= */}

      {paymentCard && (
        <div className="card-payment-panel panel">
          <div className="section-title">
            <div>
              <h2>
                Make card payment
              </h2>

              <p>
                Card ending in{" "}
                {paymentCard.last_four}
              </p>
            </div>
          </div>

          <form
            className="form"
            onSubmit={
              handlePaymentSubmit
            }
          >
            <label>
              Merchant
            </label>

            <input
              type="text"
              placeholder="Amazon"
              value={
                paymentForm.merchant
              }
              onChange={(e) =>
                setPaymentForm({
                  ...paymentForm,
                  merchant:
                    e.target.value,
                })
              }
              required
            />

            <label>
              Category
            </label>

            <select
              value={
                paymentForm.category
              }
              onChange={(e) =>
                setPaymentForm({
                  ...paymentForm,
                  category:
                    e.target.value,
                })
              }
            >
              <option>
                Shopping
              </option>

              <option>
                Food
              </option>

              <option>
                Transport
              </option>

              <option>
                Entertainment
              </option>

              <option>
                Bills
              </option>

              <option>
                Travel
              </option>

              <option>
                Other
              </option>
            </select>

            <label>
              Amount
            </label>

            <div className="amount-input">
              <span>
                $
              </span>

              <input
                type="number"
                min="0.01"
                step="0.01"
                placeholder="0.00"
                value={
                  paymentForm.amount
                }
                onChange={(e) =>
                  setPaymentForm({
                    ...paymentForm,
                    amount:
                      e.target.value,
                  })
                }
                required
              />
            </div>

            <label>
              Security PIN
            </label>

            <input
              type="password"
              inputMode="numeric"
              maxLength="4"
              placeholder="••••"
              value={
                paymentForm.pin
              }
              onChange={(e) =>
                setPaymentForm({
                  ...paymentForm,
                  pin: e.target.value,
                })
              }
              required
            />

            <div className="card-payment-actions">
              <button
                className="primary-button"
                type="submit"
                disabled={paying}
              >
                {paying
                  ? "Processing..."
                  : "Pay now"}
              </button>

              <button
                className="secondary-button"
                type="button"
                onClick={closePaymentForm}
                disabled={paying}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* =========================
          CONFIRMATION MODAL
      ========================= */}

      <ConfirmModal
        isOpen={
          confirmAction !== null
        }
        title={
          confirmAction?.type ===
          "block"
            ? "Block card?"
            : "Replace card?"
        }
        message={
          confirmAction?.type ===
          "block"
            ? `Your card ending in ${confirmAction?.card?.last_four} will be permanently blocked.`
            : `Your current card ending in ${confirmAction?.card?.last_four} will be replaced and a new card will be issued.`
        }
        confirmText={
          confirmAction?.type ===
          "block"
            ? "Block card"
            : "Replace card"
        }
        onCancel={() =>
          setConfirmAction(null)
        }
        onConfirm={() => {
          if (
            confirmAction?.type ===
            "block"
          ) {
            handleBlock(
              confirmAction.card
            );
          } else {
            handleReplace(
              confirmAction.card
            );
          }
        }}
        loading={
          updatingStatus !==
          null
        }
      />
    </>
  );
}