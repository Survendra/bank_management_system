
import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:5000/api",
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

// Beneficiary APIs
export const getBeneficiaries = () => api.get("/beneficiaries");

export const addBeneficiary = (data) =>
  api.post("/beneficiaries", data);

export const updateBeneficiary = (id, data) =>
  api.put(`/beneficiaries/${id}`, data);

export const deleteBeneficiary = (id) =>
  api.delete(`/beneficiaries/${id}`);

// Fund Transfer API
export const transferFunds = (data) =>
  api.post("/transfer", data);

export async function getNotifications() {
  const response = await api.get("/notifications");
  return response.data;
}

export async function markNotificationRead(notificationId) {
  const response = await api.patch(
    `/notifications/${notificationId}/read`
  );
  return response.data;
}

export async function markAllNotificationsRead() {
  const response = await api.patch("/notifications/read-all");
  return response.data;
}

export default api;
