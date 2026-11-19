
import { Navigate, Route, Routes } from "react-router-dom";

import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import Transaction from "./pages/Transaction";
import AccountDetails from "./pages/AccountDetails";
import Transactions from "./pages/Transactions";
import ChangePIN from "./pages/ChangePIN";
import AccountStatement from "./pages/AccountStatement";
import Beneficiaries from "./pages/Beneficiaries";
import FundTransfer from "./pages/FundTransfer";
import { ToastProvider } from "./components/Toast";
import ProfileSettings from "./pages/ProfileSettings";
import Cards from "./pages/Cards";
import ForgotPIN from "./pages/ForgotPIN";
import ScheduledTransfers from "./pages/ScheduledTransfers";
import MoneyManagement from "./pages/MoneyManagement";
import Disputes from "./pages/Disputes";
import StaffLogin from "./pages/StaffLogin";
import StaffDisputes from "./pages/StaffDisputes";
import StaffOperations from "./pages/StaffOperations";

import ProtectedRoute from "./components/ProtectedRoute";
import StaffProtectedRoute from "./components/StaffProtectedRoute";
import Layout from "./components/Layout";
import { ThemeProvider } from "./context/ThemeProvider";

function PrivateLayout() {
  return (
    <ProtectedRoute>
      <Layout />
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <Routes>
          <Route path="/" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-pin" element={<ForgotPIN />} />
          <Route path="/staff" element={<StaffLogin />} />
          <Route
            path="/staff/disputes"
            element={
              <StaffProtectedRoute>
                <StaffDisputes />
              </StaffProtectedRoute>
            }
          />
          <Route
            path="/staff/operations"
            element={
              <StaffProtectedRoute>
                <StaffOperations />
              </StaffProtectedRoute>
            }
          />

          <Route element={<PrivateLayout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/deposit" element={<Transaction type="deposit" />} />
            <Route path="/withdraw" element={<Transaction type="withdraw" />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/account" element={<AccountDetails />} />
            <Route path="/change-pin" element={<ChangePIN />} />
            <Route path="/account-statement" element={<AccountStatement />} />
            <Route path="/beneficiaries" element={<Beneficiaries />} />
            <Route path="/transfer" element={<FundTransfer />} />
            <Route path="/profile" element={<ProfileSettings />} />
            <Route path="/cards" element={<Cards />} />
            <Route path="/scheduled-transfers" element={<ScheduledTransfers />} />
            <Route path="/insights" element={<MoneyManagement />} />
            <Route path="/disputes" element={<Disputes />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ToastProvider>
    </ThemeProvider>
  );
}
