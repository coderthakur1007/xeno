"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Save, Loader2 } from "lucide-react";
import { Sidebar } from "../../components/Sidebar";
import { DataTable, Column } from "../../components/DataTable";
import { useToast } from "../../components/Toast";
import {
  fetchAdminSettings, updateAdminSetting,
  fetchFeatureFlags, fetchAuditLogs, fetchPromptTemplates,
  AuditLog,
} from "../../lib/api";

export default function AdminPage() {
  const router = useRouter();
  const { addToast } = useToast();
  const [tab, setTab] = useState<"settings" | "flags" | "prompts" | "audit">("settings");

  const [settings, setSettings] = useState<Array<{ key: string; value: unknown }>>([]);
  const [flags, setFlags] = useState<Array<{ name: string; enabled: boolean; description?: string }>>([]);
  const [prompts, setPrompts] = useState<Array<{ name: string; version: string; template: string }>>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);

  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [expandedAudit, setExpandedAudit] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("xeno_token")) {
      router.push("/login");
      return;
    }
    loadAll();
  }, [router]);

  async function loadAll() {
    try {
      const [settRes, flagRes, promptRes, auditRes] = await Promise.all([
        fetchAdminSettings().catch(() => ({ data: [] })),
        fetchFeatureFlags().catch(() => ({ data: [] })),
        fetchPromptTemplates().catch(() => ({ data: [] })),
        fetchAuditLogs().catch(() => ({ data: [] })),
      ]);
      setSettings(settRes.data);
      setFlags(flagRes.data);
      setPrompts(promptRes.data);
      setAuditLogs(auditRes.data);
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveSetting(key: string) {
    setSaving(true);
    try {
      let parsed: unknown;
      try {
        parsed = JSON.parse(editValue);
      } catch {
        parsed = editValue;
      }
      await updateAdminSetting(key, parsed);
      addToast(`Setting "${key}" updated`, "success");
      setEditingKey(null);
      loadAll();
    } catch {
      addToast("Failed to update setting", "error");
    } finally {
      setSaving(false);
    }
  }

  async function toggleFlag(name: string, currentEnabled: boolean) {
    try {
      const { api: apiFn } = await import("../../lib/api");
      await apiFn(`/api/v1/admin/feature-flags/${name}`, {
        method: "PUT",
        body: JSON.stringify({ enabled: !currentEnabled }),
      });
      setFlags((prev) =>
        prev.map((f) => (f.name === name ? { ...f, enabled: !currentEnabled } : f))
      );
      addToast(`Flag "${name}" ${!currentEnabled ? "enabled" : "disabled"}`, "success");
    } catch {
      addToast("Failed to update flag", "error");
    }
  }

  const auditColumns: Column<Record<string, unknown>>[] = [
    {
      key: "timestamp",
      label: "Time",
      render: (v) => v ? new Date(String(v)).toLocaleString() : "—",
    },
    { key: "actor", label: "Actor" },
    { key: "action", label: "Action" },
    { key: "resource", label: "Resource" },
    {
      key: "details",
      label: "Details",
      sortable: false,
      render: (v, row) => {
        const id = String(row.id || row.timestamp);
        const isExpanded = expandedAudit === id;
        return (
          <div
            className={`audit-details${isExpanded ? " expanded" : ""}`}
            onClick={() => setExpandedAudit(isExpanded ? null : id)}
          >
            {String(v || "—")}
          </div>
        );
      },
    },
  ];

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="workspace">
        <div className="page-header">
          <div className="page-header-left">
            <p className="eyebrow">System configuration</p>
            <h1>Admin</h1>
          </div>
        </div>

        <div className="tabs">
          {(["settings", "flags", "prompts", "audit"] as const).map((t) => (
            <button
              key={t}
              className={`tab${tab === t ? " active" : ""}`}
              onClick={() => setTab(t)}
            >
              {t === "settings" ? "Settings" : t === "flags" ? "Feature Flags" : t === "prompts" ? "Prompt Templates" : "Audit Logs"}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="panel">
            <div className="skeleton skeleton-text" />
            <div className="skeleton skeleton-text" />
            <div className="skeleton skeleton-card" />
          </div>
        ) : (
          <>
            {/* Settings Tab */}
            {tab === "settings" && (
              <div className="panel">
                <div className="panel-header">
                  <h3>Tenant Settings</h3>
                </div>
                {settings.length === 0 ? (
                  <div className="empty-state"><p>No settings configured</p></div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {settings.map((s) => (
                      <div key={s.key} style={{
                        display: "flex", alignItems: "flex-start", gap: 12,
                        padding: 14, background: "var(--bg-elevated)",
                        borderRadius: "var(--radius-sm)", border: "1px solid var(--line)",
                      }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--ink)", marginBottom: 4 }}>
                            {s.key}
                          </div>
                          {editingKey === s.key ? (
                            <textarea
                              className="json-editor"
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              style={{ minHeight: 100 }}
                            />
                          ) : (
                            <pre style={{
                              fontSize: "0.8125rem", color: "var(--ink-secondary)",
                              background: "var(--bg-input)", padding: 10,
                              borderRadius: "var(--radius-xs)", overflow: "auto",
                              maxHeight: 120, border: "1px solid var(--line)",
                            }}>
                              {typeof s.value === "object" ? JSON.stringify(s.value, null, 2) : String(s.value)}
                            </pre>
                          )}
                        </div>
                        {editingKey === s.key ? (
                          <button className="btn-primary" onClick={() => handleSaveSetting(s.key)} disabled={saving}>
                            {saving ? <Loader2 className="spin" /> : <Save />}
                            Save
                          </button>
                        ) : (
                          <button onClick={() => {
                            setEditingKey(s.key);
                            setEditValue(typeof s.value === "object" ? JSON.stringify(s.value, null, 2) : String(s.value));
                          }}>
                            Edit
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Feature Flags Tab */}
            {tab === "flags" && (
              <div className="panel">
                <div className="panel-header">
                  <h3>Feature Flags</h3>
                </div>
                {flags.length === 0 ? (
                  <div className="empty-state"><p>No feature flags configured</p></div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {flags.map((f) => (
                      <div key={f.name} style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between",
                        padding: "12px 16px", background: "var(--bg-elevated)",
                        borderRadius: "var(--radius-sm)", border: "1px solid var(--line)",
                      }}>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--ink)" }}>{f.name}</div>
                          {f.description && <div style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", marginTop: 2 }}>{f.description}</div>}
                        </div>
                        <button
                          className={`toggle-switch${f.enabled ? " on" : ""}`}
                          onClick={() => toggleFlag(f.name, f.enabled)}
                          aria-label={`Toggle ${f.name}`}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Prompt Templates Tab */}
            {tab === "prompts" && (
              <div className="panel">
                <div className="panel-header">
                  <h3>Prompt Templates</h3>
                </div>
                {prompts.length === 0 ? (
                  <div className="empty-state"><p>No prompt templates available</p></div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {prompts.map((p) => (
                      <div key={p.name} style={{
                        padding: 16, background: "var(--bg-elevated)",
                        borderRadius: "var(--radius-sm)", border: "1px solid var(--line)",
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                          <span style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--ink)" }}>{p.name}</span>
                          <span className="badge neutral">v{p.version}</span>
                        </div>
                        <pre style={{
                          fontSize: "0.8125rem", color: "var(--ink-secondary)",
                          background: "var(--bg-input)", padding: 12,
                          borderRadius: "var(--radius-xs)", overflow: "auto",
                          maxHeight: 160, border: "1px solid var(--line)",
                          whiteSpace: "pre-wrap", lineHeight: 1.5,
                        }}>
                          {p.template}
                        </pre>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Audit Logs Tab */}
            {tab === "audit" && (
              <div className="panel">
                <div className="panel-header">
                  <h3>Audit Logs</h3>
                </div>
                <DataTable
                  columns={auditColumns}
                  data={auditLogs as unknown as Record<string, unknown>[]}
                  emptyMessage="No audit logs available."
                />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
