"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, ChevronDown, ChevronUp } from "lucide-react";
import { Sidebar } from "../../components/Sidebar";
import { DataTable, Column } from "../../components/DataTable";
import { fetchCustomerHealth, CustomerHealth } from "../../lib/api";

export default function CustomersPage() {
  const router = useRouter();
  const [customers, setCustomers] = useState<CustomerHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("xeno_token")) {
      router.push("/login");
      return;
    }

    async function load() {
      try {
        const res = await fetchCustomerHealth();
        setCustomers(res.data);
      } catch {
        // silently handle
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [router]);

  const filtered = customers.filter((c) => {
    const q = search.toLowerCase();
    if (!q) return true;
    return (
      (c.name || "").toLowerCase().includes(q) ||
      (c.email || "").toLowerCase().includes(q) ||
      (c.customer_id || "").toLowerCase().includes(q)
    );
  });

  const riskBadge = (level: string) => {
    const l = (level || "low").toLowerCase();
    return l === "high" ? "red" : l === "medium" ? "yellow" : "green";
  };

  const columns: Column<Record<string, unknown>>[] = [
    { key: "name", label: "Name" },
    { key: "email", label: "Email" },
    {
      key: "ltv",
      label: "LTV",
      render: (v) => `₹${Number(v || 0).toLocaleString()}`,
    },
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
      label: "Risk",
      render: (v) => <span className={`badge ${riskBadge(String(v))}`}>{String(v || "Low")}</span>,
    },
    {
      key: "customer_id",
      label: "",
      sortable: false,
      render: (_, row) => {
        const cid = String(row.customer_id || "");
        const isOpen = expandedId === cid;
        return (
          <button
            className="btn-ghost"
            onClick={(e) => {
              e.stopPropagation();
              setExpandedId(isOpen ? null : cid);
            }}
            style={{ padding: "4px 8px", minHeight: "auto" }}
          >
            {isOpen ? <ChevronUp /> : <ChevronDown />}
          </button>
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
            <p className="eyebrow">Customer intelligence</p>
            <h1>Customers</h1>
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
          <div className="search-bar" style={{ flex: 1, maxWidth: 400 }}>
            <div className="search-bar-icon"><Search /></div>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or email..."
            />
          </div>
        </div>

        <div className="panel">
          {loading ? (
            <div>
              <div className="skeleton skeleton-text" />
              <div className="skeleton skeleton-text" />
              <div className="skeleton skeleton-card" />
            </div>
          ) : (
            <>
              <DataTable
                columns={columns}
                data={filtered as unknown as Record<string, unknown>[]}
                emptyMessage="No customers found."
              />
              {/* Expandable row detail */}
              {expandedId && (
                <div className="expandable-content">
                  <h4 style={{ marginBottom: 8 }}>Customer Detail</h4>
                  {(() => {
                    const c = customers.find((x) => x.customer_id === expandedId);
                    if (!c) return <p>Not found</p>;
                    return (
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
                        <div className="plan-card">
                          <span>Customer ID</span>
                          <strong style={{ fontSize: "0.8125rem" }}>{c.customer_id}</strong>
                        </div>
                        <div className="plan-card">
                          <span>Name</span>
                          <strong>{c.name || "—"}</strong>
                        </div>
                        <div className="plan-card">
                          <span>Email</span>
                          <strong style={{ fontSize: "0.8125rem" }}>{c.email || "—"}</strong>
                        </div>
                        <div className="plan-card">
                          <span>Lifetime Value</span>
                          <strong>₹{(c.ltv || 0).toLocaleString()}</strong>
                        </div>
                        <div className="plan-card">
                          <span>Churn Probability</span>
                          <strong>{((c.churn_probability || 0) * 100).toFixed(1)}%</strong>
                        </div>
                        <div className="plan-card">
                          <span>Risk Level</span>
                          <strong><span className={`badge ${riskBadge(c.risk_level)}`}>{c.risk_level}</span></strong>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
