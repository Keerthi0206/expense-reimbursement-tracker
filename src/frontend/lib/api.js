const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status, errors) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

function getToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("cdf_token");
}

async function request(path, { method = "GET", body, isForm = false } = {}) {
  const token = getToken();
  const headers = {};
  if (!isForm) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });

  if (res.status === 204) return null;

  const contentType = res.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await res.json() : null;

  if (!res.ok) {
    const message =
      (data && (data.detail || (data.errors && data.errors.map((e) => e.message).join("; ")))) ||
      `Request failed with status ${res.status}`;
    throw new ApiError(message, res.status, data && data.errors);
  }

  return data;
}

export const api = {
  login: (email, password) => request("/api/auth/login", { method: "POST", body: { email, password } }),
  me: () => request("/api/auth/me"),

  createRequest: (payload) => request("/api/requests", { method: "POST", body: payload }),
  updateRequest: (id, payload) => request(`/api/requests/${id}`, { method: "PATCH", body: payload }),
  uploadReceipt: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/api/requests/${id}/receipt`, { method: "POST", body: form, isForm: true });
  },
  // Receipts require an Authorization header, so we can't just link to the URL directly.
  // Fetch as a blob and hand back an object URL the browser can open in a new tab.
  fetchReceiptBlobUrl: async (id) => {
    const token = getToken();
    const res = await fetch(`${API_URL}/api/requests/${id}/receipt`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new ApiError("Could not load receipt", res.status);
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
  submitRequest: (id) => request(`/api/requests/${id}/submit`, { method: "POST" }),
  listRequests: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "" && v !== null)
    ).toString();
    return request(`/api/requests${qs ? `?${qs}` : ""}`);
  },
  getRequest: (id) => request(`/api/requests/${id}`),
  approveRequest: (id, comment) => request(`/api/requests/${id}/approve`, { method: "POST", body: { comment } }),
  rejectRequest: (id, reason) => request(`/api/requests/${id}/reject`, { method: "POST", body: { reason } }),
  requestInfo: (id, message) => request(`/api/requests/${id}/request-info`, { method: "POST", body: { message } }),
  cancelRequest: (id, reason) => request(`/api/requests/${id}/cancel`, { method: "POST", body: { reason } }),
  markPaid: (id) => request(`/api/requests/${id}/mark-paid`, { method: "POST" }),
  dashboard: () => request("/api/requests/stats/dashboard"),
  listRequesters: () => request("/api/requests/meta/requesters"),

  notifications: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "" && v !== null)
    ).toString();
    return request(`/api/notifications${qs ? `?${qs}` : ""}`);
  },
  markNotificationRead: (id) => request(`/api/notifications/${id}/read`, { method: "PATCH" }),

  listUsers: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "" && v !== null)
    ).toString();
    return request(`/api/admin/users${qs ? `?${qs}` : ""}`);
  },
  getUser: (id) => request(`/api/admin/users/${id}`),
  getUserHistory: (id) => request(`/api/admin/users/${id}/history?page_size=50`),
  createUser: (payload) => request("/api/admin/users", { method: "POST", body: payload }),
  updateUserRole: (id, role, reason) =>
    request(`/api/admin/users/${id}/role`, { method: "PATCH", body: { role, reason } }),
  updateUserStatus: (id, is_active, reason) =>
    request(`/api/admin/users/${id}/status`, { method: "PATCH", body: { is_active, reason } }),
};
