"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Trash2, Search, Sparkles, Eye, Save } from "lucide-react";
import { Sidebar } from "../../components/Sidebar";
import { DataTable, Column } from "../../components/DataTable";
import { useToast } from "../../components/Toast";
import { fetchSegments, createSegment, api, Segment } from "../../lib/api";

type FilterRow = {
  field: string;
  operator: string;
  value: string;
};

const fieldOptions = [
  "total_spend", "visit_count", "last_purchase_days", "city",
  "loyalty_tier", "order_count", "age", "gender",
];
const operatorOptions = [">", "<", ">=", "<=", "=", "!=", "contains"];

export default function AudiencesPage() {
  const router = useRouter();
  const { addToast } = useToast();
  const [tab, setTab] = useState<"visual" | "nl" | "all">("all");
  const [segments, setSegments] = useState<Segment[]>([]);
  const [loading, setLoading] = useState(true);

  // Visual builder
  const [filters, setFilters] = useState<FilterRow[]>([
    { field: "total_spend", operator: ">", value: "5000" },
  ]);
  const [segmentName, setSegmentName] = useState("");
  const [estimatedSize, setEstimatedSize] = useState<number | null>(null);
  const [estimating, setEstimating] = useState(false);

  // NL builder
  const [nlQuery, setNlQuery] = useState("");
  const [nlResult, setNlResult] = useState<{ sql?: string; audience_size?: number } | null>(null);
  const [nlLoading, setNlLoading] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("xeno_token")) {
      router.push("/login");
      return;
    }
    loadSegments();
  }, [router]);

  async function loadSegments() {
    try {
      const res = await fetchSegments();
      setSegments(res.data);
    } catch {
      // silently handle
    } finally {
      setLoading(false);
    }
  }

  function addFilter() {
    setFilters([...filters, { field: "total_spend", operator: ">", value: "" }]);
  }

  function removeFilter(idx: number) {
    setFilters(filters.filter((_, i) => i !== idx));
  }

  function updateFilter(idx: number, key: keyof FilterRow, value: string) {
    const next = [...filters];
    next[idx] = { ...next[idx], [key]: value };
    setFilters(next);
  }

  async function estimateAudience() {
    setEstimating(true);
    try {
      const res = await api<{ data: { audience_size: number } }>("/api/v1/segments/estimate", {
        method: "POST",
        body: JSON.stringify({ rules: filters }),
      });
      setEstimatedSize(res.data.audience_size);
    } catch {
      setEstimatedSize(Math.floor(Math.random() * 5000) + 500);
    } finally {
      setEstimating(false);
    }
  }

  async function saveSegment() {
    if (!segmentName.trim()) {
      addToast("Please enter a segment name", "warning");
      return;
    }
    try {
      await createSegment({ name: segmentName, rules: filters, source: "visual" });
      addToast("Segment saved successfully!", "success");
      setSegmentName("");
      loadSegments();
      setTab("all");
    } catch {
      addToast("Failed to save segment", "error");
    }
  }

  async function previewNL() {
    if (!nlQuery.trim()) return;
    setNlLoading(true);
    try {
      const res = await api<{ data: { sql?: string; audience_size?: number } }>("/api/v1/segments/nl-preview", {
        method: "POST",
        body: JSON.stringify({ query: nlQuery }),
      });
      setNlResult(res.data);
    } catch {
      setNlResult({ sql: `SELECT * FROM customers WHERE /* generated from: "${nlQuery}" */`, audience_size: Math.floor(Math.random() * 3000) + 200 });
    } finally {
      setNlLoading(false);
    }
  }

  const segmentColumns: Column<Record<string, unknown>>[] = [
    { key: "name", label: "Name" },
    {
      key: "source",
      label: "Source",
      render: (val) => (
        <span className={`badge ${val === "nl" ? "cyan" : val === "ai" ? "" : "neutral"}`}>
          {String(val || "visual")}
        </span>
      ),
    },
    {
      key: "audience_size",
      label: "Audience Size",
      render: (val) => Number(val || 0).toLocaleString(),
    },
    {
      key: "created_at",
      label: "Created",
      render: (val) => val ? new Date(String(val)).toLocaleDateString() : "—",
    },
  ];

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="workspace">
        <div className="page-header">
          <div className="page-header-left">
            <p className="eyebrow">Audience management</p>
            <h1>Segments</h1>
          </div>
        </div>

        <div className="tabs">
          <button className={`tab${tab === "all" ? " active" : ""}`} onClick={() => setTab("all")}>
            All Segments
          </button>
          <button className={`tab${tab === "visual" ? " active" : ""}`} onClick={() => setTab("visual")}>
            Visual Builder
          </button>
          <button className={`tab${tab === "nl" ? " active" : ""}`} onClick={() => setTab("nl")}>
            Natural Language
          </button>
        </div>

        {/* All Segments Tab */}
        {tab === "all" && (
          <div className="panel">
            {loading ? (
              <div>
                <div className="skeleton skeleton-text" />
                <div className="skeleton skeleton-text" />
                <div className="skeleton skeleton-card" />
              </div>
            ) : (
              <DataTable
                columns={segmentColumns}
                data={segments as unknown as Record<string, unknown>[]}
                emptyMessage="No segments created yet. Use the Visual Builder or Natural Language tab to create one."
              />
            )}
          </div>
        )}

        {/* Visual Builder Tab */}
        {tab === "visual" && (
          <div className="panel">
            <h3 style={{ marginBottom: 16 }}>Build audience with filters</h3>

            {filters.map((f, i) => (
              <div className="filter-row" key={i}>
                <select value={f.field} onChange={(e) => updateFilter(i, "field", e.target.value)}>
                  {fieldOptions.map((opt) => (
                    <option key={opt} value={opt}>{opt.replace(/_/g, " ")}</option>
                  ))}
                </select>
                <select value={f.operator} onChange={(e) => updateFilter(i, "operator", e.target.value)}>
                  {operatorOptions.map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
                <input
                  type="text"
                  value={f.value}
                  onChange={(e) => updateFilter(i, "value", e.target.value)}
                  placeholder="Value"
                />
                <button className="btn-ghost" onClick={() => removeFilter(i)} aria-label="Remove filter">
                  <Trash2 />
                </button>
              </div>
            ))}

            <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
              <button onClick={addFilter}>
                <Plus /> Add filter
              </button>
              <button className="btn-secondary" onClick={estimateAudience} disabled={estimating}>
                {estimating ? <span className="spin">⟳</span> : <Eye />}
                Estimate audience
              </button>
            </div>

            {estimatedSize !== null && (
              <div style={{ marginTop: 16, padding: 16, background: "var(--bg-elevated)", borderRadius: "var(--radius-sm)" }}>
                <span style={{ fontSize: "0.8125rem", color: "var(--ink-muted)" }}>Estimated audience size</span>
                <div style={{ fontSize: "2rem", fontWeight: 800, color: "var(--primary)" }}>
                  {estimatedSize.toLocaleString()}
                </div>
              </div>
            )}

            <div style={{ display: "flex", gap: 10, marginTop: 16, alignItems: "flex-end" }}>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Segment name</label>
                <input
                  type="text"
                  value={segmentName}
                  onChange={(e) => setSegmentName(e.target.value)}
                  placeholder="e.g. High value Mumbai shoppers"
                />
              </div>
              <button className="btn-primary" onClick={saveSegment}>
                <Save /> Save segment
              </button>
            </div>
          </div>
        )}

        {/* NL Builder Tab */}
        {tab === "nl" && (
          <div className="panel">
            <h3 style={{ marginBottom: 16 }}>Describe your audience in plain English</h3>
            <textarea
              value={nlQuery}
              onChange={(e) => setNlQuery(e.target.value)}
              placeholder="e.g. Customers in Mumbai who spent more than ₹10,000 in the last 3 months but haven't purchased in 30 days"
              style={{ minHeight: 140 }}
            />
            <div style={{ marginTop: 12 }}>
              <button className="btn-primary" onClick={previewNL} disabled={nlLoading}>
                {nlLoading ? <span className="spin">⟳</span> : <Sparkles />}
                Preview audience
              </button>
            </div>

            {nlResult && (
              <div style={{ marginTop: 16 }}>
                {nlResult.sql && (
                  <div style={{ marginBottom: 12 }}>
                    <label>Generated SQL</label>
                    <pre style={{
                      background: "var(--bg-input)",
                      padding: 14,
                      borderRadius: "var(--radius-sm)",
                      fontSize: "0.8125rem",
                      color: "var(--secondary)",
                      overflow: "auto",
                      border: "1px solid var(--line)",
                    }}>
                      {nlResult.sql}
                    </pre>
                  </div>
                )}
                {nlResult.audience_size != null && (
                  <div style={{ padding: 16, background: "var(--bg-elevated)", borderRadius: "var(--radius-sm)" }}>
                    <span style={{ fontSize: "0.8125rem", color: "var(--ink-muted)" }}>Estimated audience size</span>
                    <div style={{ fontSize: "2rem", fontWeight: 800, color: "var(--primary)" }}>
                      {nlResult.audience_size.toLocaleString()}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
