"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { Rocket, ArrowLeft, Loader2 } from "lucide-react";
import { Sidebar } from "../../../components/Sidebar";
import { FunnelChart, BarChart } from "../../../components/Charts";
import { useToast } from "../../../components/Toast";
import { fetchCampaign, fetchCampaignFunnel, launchCampaign, Campaign, FunnelData } from "../../../lib/api";

export default function CampaignDetailPage() {
  const router = useRouter();
  const params = useParams();
  const { addToast } = useToast();
  const id = params.id as string;

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [funnel, setFunnel] = useState<FunnelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [launching, setLaunching] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("xeno_token")) {
      router.push("/login");
      return;
    }

    async function load() {
      try {
        const [campRes, funnelRes] = await Promise.all([
          fetchCampaign(id).catch(() => null),
          fetchCampaignFunnel(id).catch(() => null),
        ]);
        if (campRes) setCampaign(campRes.data);
        if (funnelRes) setFunnel(funnelRes.data);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id, router]);

  async function handleLaunch() {
    setLaunching(true);
    try {
      await launchCampaign(id);
      addToast("Campaign launched successfully!", "success");
      setCampaign((prev) => prev ? { ...prev, status: "running" } : prev);
    } catch {
      addToast("Failed to launch campaign", "error");
    } finally {
      setLaunching(false);
    }
  }

  const statusClass = (s: string) => {
    switch (s?.toLowerCase()) {
      case "running": return "running";
      case "completed": return "completed";
      case "failed": return "failed";
      default: return "draft";
    }
  };

  const funnelSteps = funnel
    ? [
        { label: "Sent", value: funnel.sent, color: "#6C5CE7" },
        { label: "Delivered", value: funnel.delivered, color: "#8B5CF6" },
        { label: "Opened", value: funnel.opened, color: "#00D2D3" },
        { label: "Clicked", value: funnel.clicked, color: "#00E676" },
        { label: "Converted", value: funnel.converted, color: "#FFD600" },
      ]
    : [];

  const channelData = campaign?.channels
    ? campaign.channels.map((ch, i) => ({
        label: ch,
        value: Math.floor(Math.random() * 1000) + 200,
        color: ["#6C5CE7", "#00D2D3", "#00E676", "#FFD600", "#FF5252"][i % 5],
      }))
    : [];

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="workspace">
        <button className="btn-ghost" onClick={() => router.push("/campaigns")} style={{ marginBottom: 16 }}>
          <ArrowLeft /> Back to campaigns
        </button>

        {loading ? (
          <div>
            <div className="skeleton skeleton-text" style={{ width: "40%", height: 28 }} />
            <div className="skeleton skeleton-card" style={{ marginTop: 16 }} />
            <div className="skeleton skeleton-card" style={{ marginTop: 16 }} />
          </div>
        ) : campaign ? (
          <>
            <div className="page-header">
              <div className="page-header-left">
                <p className="eyebrow">Campaign detail</p>
                <h1>{campaign.name}</h1>
                <p style={{ marginTop: 4 }}>{campaign.goal}</p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span className={`status-pill ${statusClass(campaign.status)}`}>
                  {campaign.status}
                </span>
                {campaign.status?.toLowerCase() === "draft" && (
                  <button className="btn-primary" onClick={handleLaunch} disabled={launching}>
                    {launching ? <Loader2 className="spin" /> : <Rocket />}
                    Launch
                  </button>
                )}
              </div>
            </div>

            {/* Metadata */}
            <div className="metric-grid" style={{ marginTop: 20 }}>
              <div className="plan-card">
                <span>Channels</span>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
                  {campaign.channels.map((ch) => (
                    <span key={ch} className="badge cyan">{ch}</span>
                  ))}
                </div>
              </div>
              <div className="plan-card">
                <span>Created</span>
                <strong>{campaign.created_at ? new Date(campaign.created_at).toLocaleDateString() : "—"}</strong>
              </div>
              <div className="plan-card">
                <span>Status</span>
                <strong style={{ textTransform: "capitalize" }}>{campaign.status}</strong>
              </div>
              <div className="plan-card">
                <span>ID</span>
                <strong style={{ fontSize: "0.8125rem" }}>{campaign.id.slice(0, 12)}…</strong>
              </div>
            </div>

            {/* Funnel Chart */}
            {funnel && (
              <div className="panel" style={{ marginTop: 20 }}>
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Delivery funnel</p>
                    <h2>Message pipeline</h2>
                  </div>
                </div>
                <FunnelChart steps={funnelSteps} />
              </div>
            )}

            {/* Channel Breakdown */}
            {channelData.length > 0 && (
              <div className="panel" style={{ marginTop: 20 }}>
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Channel performance</p>
                    <h2>Messages by channel</h2>
                  </div>
                </div>
                <BarChart data={channelData} />
              </div>
            )}
          </>
        ) : (
          <div className="empty-state">
            <p>Campaign not found</p>
          </div>
        )}
      </main>
    </div>
  );
}
