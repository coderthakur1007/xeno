"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Users, ShoppingCart, TrendingUp, Flag, Activity } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { MetricCard } from "../components/Charts";
import { CopilotPanel } from "../components/CopilotPanel";
import { fetchAnalyticsOverview, fetchCampaigns, Campaign } from "../lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [overview, setOverview] = useState({ customers: 0, orders: 0, revenue: 0, campaigns: 0 });
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("xeno_token")) {
      router.push("/login");
      return;
    }

    async function load() {
      try {
        const [ov, camp] = await Promise.all([
          fetchAnalyticsOverview().catch(() => ({ data: { customers: 0, orders: 0, revenue: 0, campaigns: 0 } })),
          fetchCampaigns().catch(() => ({ data: [] })),
        ]);
        setOverview(ov.data);
        setCampaigns(camp.data);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [router]);

  const statusColor = (s: string) => {
    switch (s.toLowerCase()) {
      case "running": return "running";
      case "completed": return "completed";
      case "failed": return "failed";
      default: return "draft";
    }
  };

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="workspace">
        <div className="page-header">
          <div className="page-header-left">
            <p className="eyebrow">Retail &amp; D2C lifecycle CRM</p>
            <h1>Xeno AI Campaign Copilot</h1>
          </div>
          <div className="status-live">Live data</div>
        </div>

        {loading ? (
          <div className="metric-grid">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton skeleton-card" />
            ))}
          </div>
        ) : (
          <div className="metric-grid">
            <MetricCard
              icon={<Users />}
              label="Customers"
              value={overview.customers.toLocaleString()}
              trend={{ value: "+12%", direction: "up" }}
            />
            <MetricCard
              icon={<ShoppingCart />}
              label="Orders"
              value={overview.orders.toLocaleString()}
              trend={{ value: "+8%", direction: "up" }}
            />
            <MetricCard
              icon={<TrendingUp />}
              label="Revenue"
              value={`₹${Math.round(overview.revenue).toLocaleString()}`}
              trend={{ value: "+15%", direction: "up" }}
            />
            <MetricCard
              icon={<Flag />}
              label="Campaigns"
              value={overview.campaigns.toLocaleString()}
            />
          </div>
        )}

        <div className="main-grid">
          <CopilotPanel />

          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Campaign operations</p>
                <h2>Recent campaigns</h2>
              </div>
              <Flag style={{ width: 18, height: 18, color: "var(--ink-muted)" }} />
            </div>

            <div className="campaign-list">
              {campaigns.length === 0 && !loading && (
                <div className="empty-state">
                  <Activity />
                  <p>Seed the database or launch a copilot campaign to populate this board.</p>
                </div>
              )}
              {campaigns.slice(0, 6).map((campaign) => (
                <div
                  key={campaign.id}
                  className="campaign-row"
                  onClick={() => router.push(`/campaigns/${campaign.id}`)}
                >
                  <div className="campaign-row-info">
                    <strong>{campaign.name}</strong>
                    <span>{campaign.goal}</span>
                  </div>
                  <div className="campaign-row-meta">
                    <span style={{ fontSize: "0.8125rem", color: "var(--ink-muted)" }}>
                      {campaign.channels.join(", ")}
                    </span>
                    <span className={`status-pill ${statusColor(campaign.status)}`}>
                      {campaign.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="ops-grid">
          <article className="panel">
            <p className="eyebrow">Analytics fabric</p>
            <h2>Funnels, attribution, cohorts, RFM, CLV, churn</h2>
            <p style={{ marginTop: 8 }}>
              The API computes live overview metrics, RFM cohorts, campaign funnels, conversion rates,
              and anomaly flags from communication events and order behavior.
            </p>
          </article>
          <article className="panel">
            <p className="eyebrow">Configurable product surface</p>
            <h2>Settings, prompts, feature flags, rules</h2>
            <p style={{ marginTop: 8 }}>
              Tenant settings, prompt templates, and feature flags are stored in PostgreSQL so campaigns
              and AI behavior can evolve without redeploying code.
            </p>
          </article>
        </div>
      </main>
    </div>
  );
}
