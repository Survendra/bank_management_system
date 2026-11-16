import { Navigate } from "react-router-dom";

export default function ProtectedRoute({ children }) {
  const account = sessionStorage.getItem("bankAccount");
  return account ? children : <Navigate to="/" replace />;
}
