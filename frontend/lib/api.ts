const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Token management ────────────────────────────────────────── */
function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("xeno_token");
}

function setToken(token: string) {
  localStorage.setItem("xeno_token", token);
}

export function logout() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("xeno_token");
  localStorage.removeItem("xeno_email");
  localStorage.removeItem("xeno_user");
  window.location.href = "/login";
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

/* ── Core fetch wrapper ──────────────────────────────────────── */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "Bypass-Tunnel-Reminder": "true",
    ...(init?.headers as Record<string, string> || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (response.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("xeno_token");
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<T>;
}

/* ── Auth ─────────────────────────────────────────────────────── */
export async function login(email: string, password: string): Promise<{ token: string; user?: Record<string, unknown> }> {
  const res = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json", "Bypass-Tunnel-Reminder": "true" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  const token = data.token || data.data?.token || data.access_token || "";
  if (token) {
    setToken(token);
    localStorage.setItem("xeno_email", email);
    if (data.user) localStorage.setItem("xeno_user", JSON.stringify(data.user));
  }
  return { token, user: data.user };
}

export async function register(email: string, password: string, fullName: string): Promise<{ token: string }> {
  const res = await fetch(`${API_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "content-type": "application/json", "Bypass-Tunnel-Reminder": "true" },
    body: JSON.stringify({ email, password, full_name: fullName }),
  });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  const token = data.token || data.data?.token || data.access_token || "";
  if (token) {
    setToken(token);
    localStorage.setItem("xeno_email", email);
  }
  return { token };
}

/* ── Typed API functions ─────────────────────────────────────── */
export type Overview = {
  data: { customers: number; orders: number; revenue: number; campaigns: number };
};

export type Campaign = {
  id: string;
  name: string;
  goal: string;
  status: string;
  channels: string[];
  created_at: string;
  metrics: Record<string, unknown>;
};

export type Segment = {
  id: string;
  name: string;
  source: string;
  audience_size: number;
  created_at: string;
  rules?: Record<string, unknown>;
};

export type RFMRecord = {
  customer_id: string;
  recency_days: number;
  frequency: number;
  monetary: number;
  segment: string;
};

export type CohortData = {
  cohort: string;
  retention: number[];
};

export type CustomerHealth = {
  customer_id: string;
  name: string;
  email: string;
  ltv: number;
  churn_probability: number;
  risk_level: string;
};

export type FunnelData = {
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  converted: number;
};

export type AuditLog = {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  resource: string;
  details: string;
};

export function fetchAnalyticsOverview() {
  return api<Overview>("/api/v1/analytics/overview");
}

export function fetchSegments() {
  return api<{ data: Segment[] }>("/api/v1/segments");
}

export function createSegment(body: Record<string, unknown>) {
  return api<{ data: Segment }>("/api/v1/segments", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchCampaigns() {
  return api<{ data: Campaign[] }>("/api/v1/campaigns");
}

export function fetchCampaign(id: string) {
  return api<{ data: Campaign }>(`/api/v1/campaigns/${id}`);
}

export function fetchCampaignFunnel(id: string) {
  return api<{ data: FunnelData }>(`/api/v1/campaigns/${id}/funnel`);
}

export function launchCampaign(id: string) {
  return api<{ data: Campaign }>(`/api/v1/campaigns/${id}/launch`, { method: "POST" });
}

export function fetchRFM() {
  return api<{ data: RFMRecord[] }>("/api/v1/analytics/rfm");
}

export function fetchCohorts() {
  return api<{ data: CohortData[] }>("/api/v1/analytics/cohorts");
}

export function fetchCustomerHealth() {
  return api<{ data: CustomerHealth[] }>("/api/v1/analytics/customer-health");
}

export function fetchCustomers() {
  return api<{ data: Array<Record<string, unknown>> }>("/api/v1/customers");
}

export function fetchAdminSettings() {
  return api<{ data: Array<{ key: string; value: unknown }> }>("/api/v1/admin/settings");
}

export function updateAdminSetting(key: string, value: unknown) {
  return api<{ data: { key: string; value: unknown } }>(`/api/v1/admin/settings/${key}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

export function fetchFeatureFlags() {
  return api<{ data: Array<{ name: string; enabled: boolean; description?: string }> }>("/api/v1/admin/feature-flags");
}

export function fetchAuditLogs() {
  return api<{ data: AuditLog[] }>("/api/v1/admin/audit-logs");
}

export function fetchPromptTemplates() {
  return api<{ data: Array<{ name: string; version: string; template: string }> }>("/api/v1/admin/prompt-templates");
}
