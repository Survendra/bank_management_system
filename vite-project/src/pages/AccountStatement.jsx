import { useEffect, useMemo, useState } from "react";
import api from "../services/api";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

export default function AccountStatement() {
  const [transactions, setTransactions] = useState([]);
  const [account, setAccount] = useState(null);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    async function loadStatementData() {
      try {
        const [accountResponse, transactionsResponse] = await Promise.all([
          api.get("/account"),
          api.get("/transactions"),
        ]);

        setAccount(accountResponse.data.account);
        setTransactions(
          transactionsResponse.data.transactions || []
        );
      } catch (err) {
        setError(
          err.response?.data?.message ||
            "Unable to load statement data."
        );
      } finally {
        setLoading(false);
      }
    }

    loadStatementData();
  }, []);

  const filtered = useMemo(
    () =>
      transactions.filter((item) => {
        const date = new Date(item.created_at);

        if (Number.isNaN(date.getTime())) {
          return false;
        }

        const localDate = `${date.getFullYear()}-${String(
          date.getMonth() + 1
        ).padStart(2, "0")}-${String(date.getDate()).padStart(
          2,
          "0"
        )}`;

        return (
          (!fromDate || localDate >= fromDate) &&
          (!toDate || localDate <= toDate)
        );
      }),
    [transactions, fromDate, toDate]
  );

  const totals = useMemo(
    () =>
      filtered.reduce(
        (sum, item) => {
          const amount = Number(item.amount) || 0;

          if (
            item.type === "DEPOSIT" ||
            item.type === "TRANSFER_RECEIVED"
          ) {
            sum.deposits += amount;
          }

          if (
            item.type === "WITHDRAW" ||
            item.type === "TRANSFER"
          ) {
            sum.withdrawals += amount;
          }

          return sum;
        },
        {
          deposits: 0,
          withdrawals: 0,
        }
      ),
    [filtered]
  );

  function getTransactionInfo(type) {
    switch (type) {
      case "DEPOSIT":
        return {
          label: "Deposit",
          sign: "+",
        };

      case "WITHDRAW":
        return {
          label: "Withdrawal",
          sign: "-",
        };

      case "TRANSFER":
        return {
          label: "Money Sent",
          sign: "-",
        };

      case "TRANSFER_RECEIVED":
        return {
          label: "Money Received",
          sign: "+",
        };

      default:
        return {
          label: type || "Transaction",
          sign: "",
        };
    }
  }

  function downloadPDF() {
    if (!account) return;

    setDownloading(true);

    try {
      const doc = new jsPDF();

      doc.setFontSize(19);
      doc.text("BlueBank - Account Statement", 14, 20);

      doc.setFontSize(10);
      doc.text(
        `Account holder: ${account.name}`,
        14,
        30
      );

      doc.text(
        `Account number: ${account.account_number}`,
        14,
        36
      );

      doc.text(
        `Statement period: ${
          fromDate || "All dates"
        } to ${toDate || "Present"}`,
        14,
        42
      );

      doc.text(
        `Generated: ${new Date().toLocaleString()}`,
        14,
        48
      );

      autoTable(doc, {
        startY: 56,

        head: [
          [
            "Transaction ID",
            "Date & Time",
            "Type",
            "Amount",
            "Balance After",
          ],
        ],

        body: filtered.map((item) => {
          const info = getTransactionInfo(item.type);

          return [
            item.id,
            new Date(
              item.created_at
            ).toLocaleString(),

            info.label,

            `${info.sign}$${Number(
              item.amount
            ).toFixed(2)}`,

            `$${Number(
              item.balance_after
            ).toFixed(2)}`,
          ];
        }),

        styles: {
          fontSize: 8,
          cellPadding: 3,
        },

        headStyles: {
          fillColor: [36, 88, 211],
        },
      });

      const finalY =
        doc.lastAutoTable?.finalY || 65;

      doc.setFontSize(10);

      doc.text(
        `Total credits: $${totals.deposits.toFixed(2)}`,
        14,
        finalY + 10
      );

      doc.text(
        `Total debits: $${totals.withdrawals.toFixed(2)}`,
        14,
        finalY + 17
      );

      doc.text(
        `Current account balance: $${Number(
          account.balance
        ).toFixed(2)}`,
        14,
        finalY + 24
      );

      doc.save(
        `BlueBank_Statement_${account.account_number}.pdf`
      );
    } catch {
      setError(
        "Could not generate the PDF. Please try again."
      );
    } finally {
      setDownloading(false);
    }
  }

  if (loading) {
    return (
      <p className="muted">
        Loading statement data...
      </p>
    );
  }

  if (error && !account) {
    return (
      <div className="notice error">
        {error}
      </div>
    );
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            ACCOUNT DOCUMENTS
          </p>

          <h1>Account statement</h1>

          <p className="muted">
            Choose a date range and download your
            transaction statement.
          </p>
        </div>
      </div>

      <section className="panel statement-panel">
        <div className="statement-profile">
          <div>
            <span>ACCOUNT HOLDER</span>
            <strong>{account?.name}</strong>
          </div>

          <div>
            <span>ACCOUNT NUMBER</span>
            <strong>
              {account?.account_number}
            </strong>
          </div>

          <div>
            <span>CURRENT BALANCE</span>
            <strong>
              $
              {Number(
                account?.balance || 0
              ).toFixed(2)}
            </strong>
          </div>
        </div>

        <div className="statement-filters">
          <div>
            <label htmlFor="statement-from">
              From date
            </label>

            <input
              id="statement-from"
              type="date"
              value={fromDate}
              onChange={(e) =>
                setFromDate(e.target.value)
              }
            />
          </div>

          <div>
            <label htmlFor="statement-to">
              To date
            </label>

            <input
              id="statement-to"
              type="date"
              min={fromDate || undefined}
              value={toDate}
              onChange={(e) =>
                setToDate(e.target.value)
              }
            />
          </div>

          <button
            className="clear-filters"
            type="button"
            onClick={() => {
              setFromDate("");
              setToDate("");
            }}
          >
            Clear dates
          </button>
        </div>

        {error && (
          <div className="notice error">
            {error}
          </div>
        )}

        <div className="statement-summary">
          <div>
            <span>Transactions included</span>
            <strong>{filtered.length}</strong>
          </div>

          <div>
            <span>Total credits</span>
            <strong className="credit-text">
              ${totals.deposits.toFixed(2)}
            </strong>
          </div>

          <div>
            <span>Total debits</span>
            <strong className="debit-text">
              ${totals.withdrawals.toFixed(2)}
            </strong>
          </div>
        </div>

        <button
          className="primary-button statement-download"
          type="button"
          onClick={downloadPDF}
          disabled={downloading}
        >
          {downloading
            ? "Generating PDF..."
            : "↓  Download PDF statement"}
        </button>

        {filtered.length === 0 && (
          <p className="muted statement-empty">
            No transactions found for this date
            range. You can still download a statement
            showing zero transactions.
          </p>
        )}

        <p className="statement-disclaimer">
          This statement is generated from the
          transaction records currently stored in
          this practice application.
        </p>
      </section>
    </>
  );
}