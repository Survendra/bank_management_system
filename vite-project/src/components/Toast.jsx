import {
  useCallback,
  useMemo,
  useState,
} from "react";
import { ToastContext } from "./ToastContext";

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (message, type = "success", duration = 3500) => {
      const id = Date.now() + Math.random();

      setToasts((prev) => [
        ...prev,
        {
          id,
          message,
          type,
        },
      ]);

      setTimeout(() => {
        removeToast(id);
      }, duration);
    },
    [removeToast]
  );

  const value = useMemo(
    () => ({
      showToast,
      removeToast,
    }),
    [showToast, removeToast]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}

      <div className="toast-container">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast toast-${toast.type}`}
            role="alert"
          >
            <span className="toast-icon">
              {toast.type === "success" && "✓"}
              {toast.type === "error" && "!"}
              {toast.type === "warning" && "⚠"}
              {toast.type === "info" && "i"}
            </span>

            <div className="toast-content">
              <strong>
                {toast.type === "success" && "Success"}
                {toast.type === "error" && "Error"}
                {toast.type === "warning" && "Warning"}
                {toast.type === "info" && "Information"}
              </strong>

              <span>{toast.message}</span>
            </div>

            <button
              onClick={() => removeToast(toast.id)}
              aria-label="Close notification"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}