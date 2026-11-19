import { Navigate } from "react-router-dom";

export default function StaffProtectedRoute({ children }) {
  return sessionStorage.getItem("staffAuthenticated")
    ? children
    : <Navigate to="/staff" replace />;
}
