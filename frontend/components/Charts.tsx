"use client";

import { ReactNode } from "react";

/* ── MetricCard ──────────────────────────────────────────────── */
type MetricCardProps = {
  icon: ReactNode;
  label: string;
  value: string;
  trend?: { value: string; direction: "up" | "down" };
};

export function MetricCard({ icon, label, value, trend }: MetricCardProps) {
  return (
    <div className="metric-card">
      <div className="metric-card-icon">{icon}</div>
      <span className="metric-card-label">{label}</span>
      <div className="metric-card-value">{value}</div>
      {trend && (
        <span className={`metric-card-trend ${trend.direction}`}>
          {trend.direction === "up" ? "↑" : "↓"} {trend.value}
        </span>
      )}
    </div>
  );
}

/* ── BarChart (SVG) ──────────────────────────────────────────── */
type BarChartItem = {
  label: string;
  value: number;
  color?: string;
};

type BarChartProps = {
  data: BarChartItem[];
  height?: number;
};

export function BarChart({ data, height = 200 }: BarChartProps) {
  if (data.length === 0) return null;

  const maxVal = Math.max(...data.map((d) => d.value), 1);
  const barWidth = Math.min(40, Math.floor(500 / data.length) - 16);
  const chartWidth = data.length * (barWidth + 16) + 40;
  const colors = ["#6C5CE7", "#00D2D3", "#00E676", "#FFD600", "#FF5252", "#8B5CF6"];

  return (
    <div className="chart-container">
      <svg viewBox={`0 0 ${chartWidth} ${height + 40}`} preserveAspectRatio="xMidYMid meet">
        {data.map((item, i) => {
          const barH = (item.value / maxVal) * height;
          const x = 40 + i * (barWidth + 16);
          const y = height - barH;
          const color = item.color || colors[i % colors.length];

          return (
            <g key={i} className="chart-bar">
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barH}
                rx={4}
                fill={color}
                style={{
                  transformOrigin: `${x + barWidth / 2}px ${height}px`,
                  animation: `chartGrow 0.6s ease-out ${i * 0.08}s both`,
                }}
              />
              <text
                x={x + barWidth / 2}
                y={y - 6}
                textAnchor="middle"
                className="chart-value"
              >
                {item.value.toLocaleString()}
              </text>
              <text
                x={x + barWidth / 2}
                y={height + 16}
                textAnchor="middle"
                className="chart-label"
              >
                {item.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* ── FunnelChart ─────────────────────────────────────────────── */
type FunnelStep = {
  label: string;
  value: number;
  color?: string;
};

type FunnelChartProps = {
  steps: FunnelStep[];
};

export function FunnelChart({ steps }: FunnelChartProps) {
  if (steps.length === 0) return null;

  const maxVal = steps[0].value || 1;
  const colors = ["#6C5CE7", "#8B5CF6", "#00D2D3", "#00E676", "#FFD600"];

  return (
    <div className="funnel-chart">
      {steps.map((step, i) => {
        const pct = Math.max((step.value / maxVal) * 100, 8);
        const rate = i > 0 && steps[i - 1].value > 0
          ? ((step.value / steps[i - 1].value) * 100).toFixed(1)
          : null;

        return (
          <div className="funnel-step" key={i}>
            <span className="funnel-label">{step.label}</span>
            <div className="funnel-bar-wrap">
              <div
                className="funnel-bar"
                style={{
                  width: `${pct}%`,
                  background: step.color || colors[i % colors.length],
                  animation: `fadeInUp 0.4s ease-out ${i * 0.1}s both`,
                }}
              >
                {step.value.toLocaleString()}
              </div>
            </div>
            <span className="funnel-value">
              {rate ? `${rate}%` : "100%"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ── HeatmapCell ─────────────────────────────────────────────── */
type HeatmapCellProps = {
  value: number;
  maxValue?: number;
  label?: string;
};

export function HeatmapCell({ value, maxValue = 100, label }: HeatmapCellProps) {
  const ratio = Math.min(value / (maxValue || 1), 1);
  const r = Math.round(255 * (1 - ratio));
  const g = Math.round(200 * ratio);
  const bg = `rgba(${r}, ${g}, 80, ${0.3 + ratio * 0.7})`;

  return (
    <div
      className="heatmap-cell"
      style={{ background: bg }}
      title={`${label || ""}: ${value}%`}
    >
      {label ?? `${Math.round(value)}%`}
    </div>
  );
}

/* ── MiniSparkline ───────────────────────────────────────────── */
type MiniSparklineProps = {
  values: number[];
  color?: string;
};

export function MiniSparkline({ values, color = "#6C5CE7" }: MiniSparklineProps) {
  if (values.length < 2) return null;

  const w = 60;
  const h = 20;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;

  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <span className="sparkline">
      <svg viewBox={`0 0 ${w} ${h}`}>
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
