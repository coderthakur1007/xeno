"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Users, TrendingUp, ShoppingCart, Activity } from "lucide-react";
import { Sidebar } from "../../components/Sidebar";
import { MetricCard, BarChart, HeatmapCell } from "../../components/Charts";
import { DataTable, Column } from "../../components/DataTable";
import {
  fetchAnalyticsOverview, fetchRFM, fetchCohorts, fetchCustomerHealth,
  RFMRecord, CohortData, CustomerHealth,
} from "../../lib/api";

export default function AnalyticsPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"overview" | "rfm" | "cohort" | "health">("overview");
  const [overview, setOverview] = useState({ customers: 0, orders: 0, revenue: 0, campaigns: 0 });
  const [rfm, setRfm] = useState<RFMRecord[]>([]);
  const [cohorts, setCohorts] = useState<CohortData[]>([]);
  const [health, setHealth] = useState<CustomerHealth[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("xeno_token")) {
      router.push("/login");
      return;
    }
    loadData();
  }, [router]);

  async function loadData() {
    try {
      const [ov, rfmRes, cohortRes, healthRes] = await Promise.all([
        fetchAnalyticsOverview().catch(() => ({ data: { customers: 0, orders: 0, revenue: 0, campaigns: 0 } })),
        fetchRFM().catch(() => ({ data: [] })),
        fetchCohorts().catch(() => ({ data: [] })),
        fetchCustomerHealth().catch(() => ({ data: [] })),
      ]);
      setOverview(ov.data);
      setRfm(rfmRes.data);
      setCohorts(cohortRes.data);
      setHealth(healthRes.data);
    } finally {
      setLoading(false);
    }
  }

  const segmentBadge = (seg: string) => {
    const s = seg.toLowerCase();
    if (s.includes("champion")) return "green";
    if (s.includes("loyal")) return "cyan";
    if (s.includes("risk")) return "yellow";
    if (s.includes("lost")) return "red";
    return "neutral";
  };

  const rfmColumns: Column<Record<string, unknown>>[] = [
    { key: "customer_id", label: "Customer ID", render: (v) => String(v).slice(0, 10) + "…" },
    { key: "recency_days", label: "Recency (days)" },
    { key: "frequency", label: "Frequency" },
    { key: "monetary", label: "Monetary", render: (v) => `₹${Number(v || 0).toLocaleString()}` },
    {
      key: "segment",
      label: "Segment",
      render: (v) => <span className={`badge ${segmentBadge(String(v))}`}>{String(v)}</span>,
    },
  ];

  const healthColumns: Column<Record<string, unknown>>[] = [
    { key: "name", label: "Name" },
    { key: "ltv", label: "LTV", render: (v) => `₹${Number(v || 0).toLocaleString()}` },
    {
      key: "churn_probability",
      label: "Churn Risk",
      render: (v) => {
        const pct = Number(v || 0) * 100;
        const color = pct > 70 ? "red" : pct > 40 ? "yellow" : "green";
        return (
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 120 }}>
            <div className="progress-bar" style={{ flex: 1 }}>
              <div className={`progress-bar-fill ${color}`} style={{ width: `${pct}%` }} />
            </div>
            <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>{pct.toFixed(0)}%</span>
          </div>
        );
      },
    },
    {
      key: "risk_level",
      label: "Risk Level",
      render: (v) => {
        const level = String(v || "low").toLowerCase();
        const cls = level === "high" ? "red" : level === "medium" ? "yellow" : "green";
        return <span className={`badge ${cls}`}>{String(v)}</span>;
      },
    },
  ];

  const topMetrics = [
    { label: "Customers", value: overview.customers, color: "#6C5CE7" },
    { label: "Orders", value: overview.orders, color: "#00D2D3" },
    { label: "Revenue", value: Math.round(overview.revenue), color: "#00E676" },
    { label: "Campaigns", value: overview.campaigns, color: "#FFD600" },
  ];

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="workspace">
        <div className="page-header">
          <div className="page-header-left">
            <p className="eyebrow">Data intelligence</p>
            <h1>Analytics</h1>
          </div>
        </div>

        <div className="tabs">
          {(["overview", "rfm", "cohort", "health"] as const).map((t) => (
            <button
              key={t}
              className={`tab${tab === t ? " active" : ""}`}
              onClick={() => setTab(t)}
            >
              {t === "overview" ? "Overview" : t === "rfm" ? "RFM Analysis" : t === "cohort" ? "Cohort Retention" : "Customer Health"}
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
            {/* Overview Tab */}
            {tab === "overview" && (
              <>
                <div className="metric-grid">
                  <MetricCard icon={<Users />} label="Customers" value={overview.customers.toLocaleString()} />
                  <MetricCard icon={<ShoppingCart />} label="Orders" value={overview.orders.toLocaleString()} />
                  <MetricCard icon={<TrendingUp />} label="Revenue" value={`₹${Math.round(overview.revenue).toLocaleString()}`} />
                  <MetricCard icon={<Activity />} label="Campaigns" value={overview.campaigns.toLocaleString()} />
                </div>
                <div className="panel" style={{ marginTop: 20 }}>
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">Key metrics</p>
                      <h2>Performance overview</h2>
                    </div>
                  </div>
                  <BarChart data={topMetrics} height={220} />
                </div>
              </>
            )}

            {/* RFM Tab */}
            {tab === "rfm" && (
              <div className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Customer segmentation</p>
                    <h2>RFM Analysis</h2>
                  </div>
                </div>
                <DataTable
                  columns={rfmColumns}
                  data={rfm as unknown as Record<string, unknown>[]}
                  emptyMessage="No RFM data available. Ensure the analytics pipeline has run."
                />
              </div>
            )}

            {/* Cohort Tab */}
            {tab === "cohort" && (
              <div className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Retention analysis</p>
                    <h2>Cohort Retention</h2>
                  </div>
                </div>
                {cohorts.length === 0 ? (
                  <div className="empty-state">
                    <p>No cohort data available</p>
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <div style={{ display: "grid", gap: 2, minWidth: cohorts[0]?.retention?.length ? (cohorts[0].retention.length + 1) * 56 : 400 }}>
                      {/* Header */}
                      <div style={{ display: "flex", gap: 2 }}>
                        <div className="heatmap-header" style={{ minWidth: 90 }}>Cohort</div>
                        {cohorts[0]?.retention?.map((_, i) => (
                          <div key={i} className="heatmap-header">M{i}</div>
                        ))}
                      </div>
                      {/* Rows */}
                      {cohorts.map((cohort, ri) => (
                        <div key={ri} style={{ display: "flex", gap: 2 }}>
                          <div className="heatmap-header" style={{ minWidth: 90, fontSize: "0.625rem" }}>
                            {cohort.cohort}
                          </div>
                          {cohort.retention.map((val, ci) => (
                            <HeatmapCell key={ci} value={val} maxValue={100} />
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Health Tab */}
            {tab === "health" && (
              <div className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Predictive analytics</p>
                    <h2>Customer Health</h2>
                  </div>
                </div>
                <DataTable
                  columns={healthColumns}
                  data={health as unknown as Record<string, unknown>[]}
                  emptyMessage="No customer health data available."
                />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
