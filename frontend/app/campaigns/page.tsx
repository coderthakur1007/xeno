"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { Sidebar } from "../../components/Sidebar";
import { DataTable, Column } from "../../components/DataTable";
import { fetchCampaigns, Campaign } from "../../lib/api";

const statusFilters = ["all", "draft", "running", "completed", "failed"] as const;

export default function CampaignsPage() {
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("xeno_token")) {
      router.push("/login");
      return;
    }

    async function load() {
      try {
        const res = await fetchCampaigns();
        setCampaigns(res.data);
      } catch {
        // silently handle
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [router]);

  const filtered = statusFilter === "all"
    ? campaigns
    : campaigns.filter((c) => c.status.toLowerCase() === statusFilter);

  const columns: Column<Record<string, unknown>>[] = [
    { key: "name", label: "Name" },
    {
      key: "goal",
      label: "Goal",
      render: (val) => (
        <span style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>
          {String(val || "")}
        </span>
      ),
    },
    {
      key: "channels",
      label: "Channels",
      sortable: false,
      render: (val) => {
        const channels = Array.isArray(val) ? val : [];
        return (
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {channels.map((ch: string) => (
              <span key={ch} className="badge cyan">{ch}</span>
            ))}
          </div>
        );
      },
    },
    {
      key: "status",
      label: "Status",
      render: (val) => {
        const s = String(val || "draft").toLowerCase();
        return <span className={`status-pill ${s}`}>{val as string}</span>;
      },
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
            <p className="eyebrow">Campaign management</p>
            <h1>Campaigns</h1>
          </div>
          <button className="btn-primary" onClick={() => router.push("/")}>
            <Plus /> Create Campaign
          </button>
        </div>

        <div className="tabs">
          {statusFilters.map((s) => (
            <button
              key={s}
              className={`tab${statusFilter === s ? " active" : ""}`}
              onClick={() => setStatusFilter(s)}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>

        <div className="panel">
          {loading ? (
            <div>
              <div className="skeleton skeleton-text" />
              <div className="skeleton skeleton-text" />
              <div className="skeleton skeleton-card" />
            </div>
          ) : (
            <DataTable
              columns={columns}
              data={filtered as unknown as Record<string, unknown>[]}
              emptyMessage="No campaigns found. Create one from the dashboard."
              onRowClick={(row) => router.push(`/campaigns/${row.id}`)}
            />
          )}
        </div>
      </main>
    </div>
  );
}
