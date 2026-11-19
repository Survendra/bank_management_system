import { useEffect, useRef, useState } from "react";
import api from "../services/api";
import { useToast } from "../components/useToast";

const categories = [
  "Bills",
  "Education",
  "Entertainment",
  "Food",
  "Health",
  "Shopping",
  "Transport",
  "Travel",
  "Other",
];

export default function MoneyManagement() {
  const [insights, setInsights] = useState(null);
  const [goalForm, setGoalForm] = useState({
    name: "",
    target_amount: "",
    target_date: "",
  });
  const [budgetForm, setBudgetForm] = useState({
    category: "Food",
    amount: "",
  });
  const [goalAmounts, setGoalAmounts] = useState({});
  const [workingGoalId, setWorkingGoalId] = useState("");
  const workingGoalIdRef = useRef("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { showToast } = useToast();

  async function loadInsights() {
    try {
      const response = await api.get("/insights");
      setInsights(response.data);
    } catch (error) {
      showToast(
        error.response?.data?.message || "Could not load spending insights.",
        "error"
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    api.get("/insights")
      .then((response) => {
        if (active) {
          setInsights(response.data);
        }
      })
      .catch((error) =>
        showToast(
          error.response?.data?.message || "Could not load spending insights.",
          "error"
        )
      )
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [showToast]);

  async function saveBudget(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await api.put(`/budgets/${encodeURIComponent(budgetForm.category)}`, {
        amount: budgetForm.amount,
      });
      setBudgetForm({ ...budgetForm, amount: "" });
      showToast("Monthly budget saved.", "success");
      await loadInsights();
    } catch (error) {
      showToast(
        error.response?.data?.message || "Could not save this budget.",
        "error"
      );
    } finally {
      setSaving(false);
    }
  }

  async function removeBudget(category) {
    try {
      await api.delete(`/budgets/${encodeURIComponent(category)}`);
      showToast("Budget removed.", "success");
      await loadInsights();
    } catch (error) {
      showToast(
        error.response?.data?.message || "Could not remove this budget.",
        "error"
      );
    }
  }

  async function createGoal(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await api.post("/savings-goals", goalForm);
      setGoalForm({ name: "", target_amount: "", target_date: "" });
      showToast("Savings goal created.", "success");
      await loadInsights();
    } catch (error) {
      showToast(
        error.response?.data?.message || "Could not create this goal.",
        "error"
      );
    } finally {
      setSaving(false);
    }
  }

  async function changeGoal(goalId, action) {
    const amount = goalAmounts[goalId];
    if (!amount) {
      showToast("Enter an amount first.", "warning");
      return;
    }
    if (workingGoalIdRef.current) {
      return;
    }
    workingGoalIdRef.current = goalId;
    setWorkingGoalId(goalId);
    try {
      await api.post(`/savings-goals/${goalId}/${action}`, { amount });
      setGoalAmounts((current) => ({ ...current, [goalId]: "" }));
      showToast(
        action === "contribute" ? "Amount allocated to your goal." : "Amount returned to available funds.",
        "success"
      );
      await loadInsights();
    } catch (error) {
      showToast(
        error.response?.data?.message || "Could not update this savings goal.",
        "error"
      );
    } finally {
      workingGoalIdRef.current = "";
      setWorkingGoalId("");
    }
  }

  if (loading) {
    return <p className="muted">Loading spending insights...</p>;
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PLAN YOUR MONEY</p>
          <h1>Spending &amp; savings</h1>
          <p className="muted">
            See this month’s spending, set category budgets and build savings goals.
          </p>
        </div>
      </div>

      <section className="summary-grid feature-summary">
        <article className="info-card">
          <span className="info-label">Spending this month</span>
          <strong>${Number(insights?.total_spending || 0).toFixed(2)}</strong>
          <small>{insights?.month || ""}</small>
        </article>
        <article className="info-card">
          <span className="info-label">Available to spend</span>
          <strong>${Number(insights?.available_balance || 0).toFixed(2)}</strong>
          <small>After savings-goal allocations</small>
        </article>
        <article className="info-card">
          <span className="info-label">Tracked categories</span>
          <strong>{insights?.categories?.length || 0}</strong>
          <small>Completed account activity only</small>
        </article>
      </section>

      <div className="feature-columns">
        <section className="panel feature-panel">
          <h2>Spending by category</h2>
          {!insights?.categories?.length ? (
            <p className="muted">Completed spending will appear here.</p>
          ) : (
            <div className="feature-record-list">
              {insights.categories.map((item) => (
                <article className="feature-record" key={item.category}>
                  <strong>{item.category}</strong>
                  <span>${Number(item.spent).toFixed(2)}</span>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="panel feature-panel">
          <h2>Monthly category budgets</h2>
          <form className="feature-form compact" onSubmit={saveBudget}>
            <label>
              Category
              <select
                value={budgetForm.category}
                onChange={(event) =>
                  setBudgetForm({ ...budgetForm, category: event.target.value })
                }
              >
                {categories.map((category) => (
                  <option key={category}>{category}</option>
                ))}
              </select>
            </label>
            <label>
              Monthly limit
              <input
                type="number"
                min="0.01"
                max="5000000000"
                step="0.01"
                value={budgetForm.amount}
                onChange={(event) =>
                  setBudgetForm({ ...budgetForm, amount: event.target.value })
                }
                required
              />
            </label>
            <button className="primary-button" disabled={saving}>
              Save budget
            </button>
          </form>
          <div className="feature-record-list">
            {(insights?.budgets || []).map((budget) => {
              const progress = Math.min(
                100,
                (Number(budget.spent) / Number(budget.limit)) * 100
              );
              return (
                <article className="budget-record" key={budget.category}>
                  <div className="feature-record">
                    <strong>{budget.category}</strong>
                    <span>
                      ${Number(budget.spent).toFixed(2)} / ${Number(budget.limit).toFixed(2)}
                    </span>
                  </div>
                  <div className="budget-track">
                    <span style={{ width: `${Number.isFinite(progress) ? progress : 0}%` }} />
                  </div>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => removeBudget(budget.category)}
                  >
                    Remove budget
                  </button>
                </article>
              );
            })}
          </div>
        </section>
      </div>

      <section className="panel feature-panel feature-list-panel">
        <div className="history-heading">
          <div>
            <h2>Savings goals</h2>
            <p>Goal allocations are reserved from available funds; they do not move money to an external account.</p>
          </div>
        </div>
        <form className="feature-form goal-form" onSubmit={createGoal}>
          <label>
            Goal name
            <input
              value={goalForm.name}
              maxLength={80}
              onChange={(event) =>
                setGoalForm({ ...goalForm, name: event.target.value })
              }
              required
            />
          </label>
          <label>
            Target amount
            <input
              type="number"
              min="0.01"
              max="5000000000"
              step="0.01"
              value={goalForm.target_amount}
              onChange={(event) =>
                setGoalForm({ ...goalForm, target_amount: event.target.value })
              }
              required
            />
          </label>
          <label>
            Target date
            <input
              type="date"
              value={goalForm.target_date}
              onChange={(event) =>
                setGoalForm({ ...goalForm, target_date: event.target.value })
              }
            />
          </label>
          <button className="primary-button" disabled={saving}>
            Create goal
          </button>
        </form>
        <div className="feature-record-list">
          {(insights?.savings_goals || []).map((goal) => {
            const progress = Math.min(
              100,
              (Number(goal.saved_amount) / Number(goal.target_amount)) * 100
            );
            return (
              <article className="goal-record" key={goal.id}>
                <div className="feature-record">
                  <div>
                    <strong>{goal.name}</strong>
                    <small>
                      ${Number(goal.saved_amount).toFixed(2)} of ${Number(goal.target_amount).toFixed(2)}
                      {goal.target_date ? ` · target ${goal.target_date}` : ""}
                    </small>
                  </div>
                  <span>{Math.round(Number.isFinite(progress) ? progress : 0)}%</span>
                </div>
                <div className="budget-track">
                  <span style={{ width: `${Number.isFinite(progress) ? progress : 0}%` }} />
                </div>
                <div className="goal-actions">
                  <input
                    type="number"
                    min="0.01"
                    max="5000000000"
                    step="0.01"
                    placeholder="Amount"
                    disabled={workingGoalId === goal.id}
                    value={goalAmounts[goal.id] || ""}
                    onChange={(event) =>
                      setGoalAmounts((current) => ({
                        ...current,
                        [goal.id]: event.target.value,
                      }))
                    }
                  />
                  <button type="button" className="secondary-button" disabled={workingGoalId === goal.id} onClick={() => changeGoal(goal.id, "contribute")}>
                    Allocate
                  </button>
                  <button type="button" className="secondary-button" disabled={workingGoalId === goal.id} onClick={() => changeGoal(goal.id, "withdraw")}>
                    Return
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </>
  );
}
