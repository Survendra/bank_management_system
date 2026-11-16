
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

import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";

function PrivateLayout() {
  return (
    <ProtectedRoute>
      <Layout />
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-pin" element={<ForgotPIN />} />

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
          <Route path="/profile" element={<ProfileSettings />}/>
          <Route path="/cards" element={<Cards />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ToastProvider>
  );
}
