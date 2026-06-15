"use client";

import { useState } from "react";
import { Bot, Download, Loader2, Rocket, Sparkles, Table2, CheckCircle, Circle } from "lucide-react";
import { api } from "../lib/api";

type ChannelContent = {
  subject?: string;
  body?: string;
  cta?: string;
};

type Variant = {
  key: string;
  angle: string;
  why: string;
  channel?: string;
  channels?: string[];
  subject?: string;
  body?: string;
  cta?: string;
  content?: Record<string, ChannelContent>;
};

type Plan = {
  data: {
    audience_size: number;
    conversion_probability?: number;
    expected_conversions?: number;
    recommended_channels?: string[];
    strategy: {
      channels?: string[];
      conversion_probability: number;
      expected_conversions: number;
      send_window?: string;
    };
    variants: Variant[];
    explainability: string[];
    analytics_insights?: string[];
    execution_readiness?: {
      ready: boolean;
      checks?: string[];
    };
  };
};

type ProofRow = {
  prompt: string;
  audience_size: number;
  detected_intents: string;
  channels: string;
  conversion_probability: number;
  expected_conversions: number;
};

const agentSteps = [
  { name: "Intent", key: "intent" },
  { name: "Audience", key: "audience" },
  { name: "Strategy", key: "strategy" },
  { name: "Creative", key: "creative" },
  { name: "Orchestrate", key: "orchestrate" },
];

const promptExamples = [
  "Bring back customers who have not purchased in 90 days.",
  "Find high value shoppers and launch an exclusive drop.",
  "Convert new shoppers into second-purchase customers.",
  "Win back platinum skincare buyers in Mumbai with WhatsApp.",
  "Target email customers who clicked but have not converted.",
  "Prevent churn among loyal customers inactive for 60 days.",
  "Promote footwear sale to gold tier shoppers in Bangalore.",
  "Recover customers with failed SMS deliveries.",
  "Grow average order value for grocery buyers with a bundle offer.",
  "Invite recent first-time women shoppers to a second purchase campaign.",
  "Launch an RCS campaign for engaged apparel customers.",
  "Reward campaign buyers who converted after the last promotion.",
];

export function CopilotPanel() {
  const [goal, setGoal] = useState("Increase repeat purchases from customers inactive for 90 days");
  const [plan, setPlan] = useState<Plan["data"] | null>(null);
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [proof, setProof] = useState<ProofRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [proofLoading, setProofLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState(-1);

  async function createPlan() {
    setLoading(true);
    setError(null);
    setPlan(null);
    setActiveAgent(0);

    try {
      // Simulate agent pipeline progression
      const agentInterval = setInterval(() => {
        setActiveAgent((prev) => {
          if (prev >= agentSteps.length - 1) {
            clearInterval(agentInterval);
            return prev;
          }
          return prev + 1;
        });
      }, 800);

      const response = await api<Plan>("/api/v1/copilot/plan", {
        method: "POST",
        body: JSON.stringify({ goal }),
      });

      clearInterval(agentInterval);
      setActiveAgent(agentSteps.length);
      setPlan(response.data);
    } catch (err) {
      setActiveAgent(-1);
      setError(err instanceof Error ? err.message : "Unable to create plan");
    } finally {
      setLoading(false);
    }
  }

  async function draftAndLaunch() {
    setLaunching(true);
    setError(null);
    try {
      const draft = await api<{ data: { id: string } }>("/api/v1/campaigns/from-goal", {
        method: "POST",
        body: JSON.stringify({ goal }),
      });
      setCampaignId(draft.data.id);
      await api(`/api/v1/campaigns/${draft.data.id}/launch`, { method: "POST" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to draft or launch campaign");
    } finally {
      setLaunching(false);
    }
  }

  async function runProof() {
    setProofLoading(true);
    setError(null);
    try {
      const response = await api<{ data: ProofRow[] }>("/api/v1/copilot/proof");
      setProof(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run proof matrix");
    } finally {
      setProofLoading(false);
    }
  }

  function downloadExcel() {
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    window.open(`${base}/api/v1/reports/copilot-proof.xlsx`, "_blank", "noopener,noreferrer");
  }

  return (
    <section className="copilot-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Multi-agent copilot</p>
          <h2>Autonomous campaign planner</h2>
        </div>
        <Bot style={{ width: 20, height: 20, color: "var(--primary)" }} aria-hidden />
      </div>

      <textarea
        value={goal}
        onChange={(event) => setGoal(event.target.value)}
        placeholder="Describe your campaign goal..."
      />

      <div className="prompt-chips">
        {promptExamples.map((prompt) => (
          <button className="chip" key={prompt} onClick={() => setGoal(prompt)}>
            {prompt}
          </button>
        ))}
      </div>

      <div className="copilot-actions">
        <button onClick={createPlan} disabled={loading}>
          {loading ? <Loader2 className="spin" /> : <Sparkles />}
          Plan
        </button>
        <button className="btn-primary" onClick={draftAndLaunch} disabled={launching}>
          {launching ? <Loader2 className="spin" /> : <Rocket />}
          Draft &amp; launch
        </button>
        <button onClick={runProof} disabled={proofLoading}>
          {proofLoading ? <Loader2 className="spin" /> : <Table2 />}
          Proof matrix
        </button>
        <button onClick={downloadExcel}>
          <Download />
          Excel
        </button>
      </div>

      {/* Agent Pipeline */}
      {activeAgent >= 0 && (
        <div className="agent-pipeline">
          {agentSteps.map((step, i) => (
            <span key={step.key} style={{ display: "contents" }}>
              <div className="agent-step">
                <div
                  className={`agent-step-dot${
                    i < activeAgent ? " done" : i === activeAgent && loading ? " active" : ""
                  }`}
                >
                  {i < activeAgent ? (
                    <CheckCircle style={{ width: 14, height: 14 }} />
                  ) : (
                    <Circle style={{ width: 14, height: 14 }} />
                  )}
                </div>
                <span className="agent-step-label">{step.name}</span>
              </div>
              {i < agentSteps.length - 1 && (
                <div className={`agent-connector${i < activeAgent ? " done" : ""}`} />
              )}
            </span>
          ))}
        </div>
      )}

      {error && <p className="error-box">{error}</p>}

      {/* Plan Results */}
      {plan && (
        <>
          <div className="plan-grid">
            <div className="plan-card">
              <span>Audience</span>
              <strong>{(plan.audience_size || 0).toLocaleString()}</strong>
            </div>
            <div className="plan-card">
              <span>Conv. probability</span>
              <strong>{((plan.conversion_probability || plan.strategy?.conversion_probability || 0) * 100).toFixed(1)}%</strong>
            </div>
            <div className="plan-card">
              <span>Expected conversions</span>
              <strong>{(plan.expected_conversions || plan.strategy?.expected_conversions || 0).toLocaleString()}</strong>
            </div>
            <div className="plan-card">
              <span>Channels</span>
              <strong>{(plan.recommended_channels || plan.strategy?.channels || []).join(", ")}</strong>
            </div>
          </div>

          {/* Variants */}
          {plan.variants && plan.variants.length > 0 && (
            <div className="variant-cards">
              {plan.variants.map((v, i) => {
                /* Handle both flat and nested content structures */
                const flatBody = v.body;
                const flatSubject = v.subject;
                const flatCta = v.cta;
                const channels = v.channels || (v.content ? Object.keys(v.content) : []);
                const hasNestedContent = v.content && typeof v.content === "object";

                return (
                  <div className="variant-card" key={i}>
                    <div className="variant-card-header">
                      <strong>Variant {v.key || String.fromCharCode(65 + i)}</strong>
                      {channels.length > 0 && (
                        <div style={{ display: "flex", gap: 4 }}>
                          {channels.map((ch) => (
                            <span key={ch} className="badge cyan">{ch}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <p style={{ fontWeight: 600, color: "var(--ink)", textTransform: "capitalize" }}>
                      {v.angle?.replace(/_/g, " ")}
                    </p>

                    {/* Flat content (simple variant) */}
                    {!hasNestedContent && flatSubject && (
                      <p><strong style={{ fontSize: "0.75rem" }}>Subject:</strong> {flatSubject}</p>
                    )}
                    {!hasNestedContent && flatBody && <p>{flatBody}</p>}
                    {!hasNestedContent && flatCta && (
                      <span className="badge" style={{ alignSelf: "flex-start" }}>{flatCta}</span>
                    )}

                    {/* Nested content (channel-specific) */}
                    {hasNestedContent && Object.entries(v.content!).map(([ch, msg]) => (
                      <div key={ch} style={{
                        marginTop: 8,
                        padding: "10px 12px",
                        background: "var(--bg-elevated)",
                        borderRadius: "var(--radius-sm)",
                        borderLeft: "3px solid var(--secondary)",
                      }}>
                        <p style={{ fontSize: "0.6875rem", fontWeight: 700, color: "var(--secondary)", textTransform: "uppercase", marginBottom: 4 }}>
                          {ch}
                        </p>
                        {msg.subject && (
                          <p style={{ fontSize: "0.8125rem" }}>
                            <strong style={{ fontSize: "0.75rem", color: "var(--ink-muted)" }}>Subject:</strong> {msg.subject}
                          </p>
                        )}
                        <p style={{ fontSize: "0.8125rem", marginTop: 4, color: "var(--ink)" }}>
                          {msg.body}
                        </p>
                        {msg.cta && (
                          <span className="badge" style={{ alignSelf: "flex-start", marginTop: 6 }}>
                            {msg.cta}
                          </span>
                        )}
                      </div>
                    ))}

                    <p style={{ fontStyle: "italic", fontSize: "0.75rem", color: "var(--ink-faint)", marginTop: 8 }}>
                      {v.why}
                    </p>
                  </div>
                );
              })}
            </div>
          )}

          {/* Explainability */}
          <div className="insights">
            {plan.explainability.slice(0, 5).map((item, i) => (
              <p className="insight-item" key={i}>
                {item}
              </p>
            ))}
          </div>

          {/* Analytics insights */}
          {plan.analytics_insights && plan.analytics_insights.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <p className="eyebrow">Analytics insights</p>
              <div className="insights">
                {plan.analytics_insights.map((insight, i) => (
                  <p className="insight-item" key={i} style={{ borderLeftColor: "var(--secondary)" }}>
                    {insight}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Execution readiness */}
          {plan.execution_readiness && (
            <div style={{ marginTop: 12 }}>
              <div
                className={`success-msg`}
                style={{
                  borderLeftColor: plan.execution_readiness.ready ? "var(--success)" : "var(--warning)",
                  background: plan.execution_readiness.ready
                    ? "rgba(0,230,118,0.08)"
                    : "rgba(255,214,0,0.08)",
                  color: plan.execution_readiness.ready ? "var(--success)" : "var(--warning)",
                }}
              >
                {plan.execution_readiness.ready
                  ? "✓ Campaign is ready for execution"
                  : "⚠ Campaign needs attention before execution"}
              </div>
              {plan.execution_readiness.checks && (
                <ul style={{ marginTop: 8, paddingLeft: 20, fontSize: "0.8125rem", color: "var(--ink-muted)" }}>
                  {plan.execution_readiness.checks.map((c, i) => (
                    <li key={i} style={{ marginBottom: 4, listStyle: "disc" }}>{c}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}

      {campaignId && (
        <p className="success-msg">
          Campaign {campaignId.slice(0, 8)} is running through the simulator.
        </p>
      )}

      {/* Proof Table */}
      {proof.length > 0 && (
        <div className="proof-table">
          <div className="proof-header">
            <span>Prompt</span>
            <span>Intent</span>
            <span>Audience</span>
            <span>Forecast</span>
          </div>
          {proof.slice(0, 8).map((row, i) => (
            <div className="proof-row" key={i}>
              <span>{row.prompt}</span>
              <span>{row.detected_intents}</span>
              <strong>{row.audience_size.toLocaleString()}</strong>
              <strong>{row.expected_conversions.toLocaleString()}</strong>
            </div>
          ))}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !plan && (
        <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="skeleton skeleton-text" style={{ width: "100%" }} />
          <div className="skeleton skeleton-text" style={{ width: "80%" }} />
          <div className="skeleton skeleton-text" style={{ width: "60%" }} />
          <div className="skeleton skeleton-card" style={{ marginTop: 8 }} />
        </div>
      )}
    </section>
  );
}
