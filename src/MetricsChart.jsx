// src/MetricsChart.jsx
// Renders live Accuracy vs Rounds and Loss vs Rounds charts.
// Uses only vanilla Canvas API – no extra dependencies needed.
import { useRef, useEffect } from "react";

const W = 480, H = 160, PAD = { top: 16, right: 16, bottom: 36, left: 48 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top  - PAD.bottom;

function drawChart(canvas, data, key, color, label) {
  if (!canvas || data.length === 0) return;
  const ctx  = canvas.getContext("2d");
  const dpr  = window.devicePixelRatio || 1;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width  = W + "px";
  canvas.style.height = H + "px";
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const vals = data.map((d) => d[key]);
  const min  = 0;
  const max  = 1;

  // Axes
  ctx.strokeStyle = "rgba(120,140,100,0.4)";
  ctx.lineWidth   = 1;
  ctx.beginPath();
  ctx.moveTo(PAD.left, PAD.top);
  ctx.lineTo(PAD.left, PAD.top + PLOT_H);
  ctx.lineTo(PAD.left + PLOT_W, PAD.top + PLOT_H);
  ctx.stroke();

  // Y gridlines
  ctx.setLineDash([3, 4]);
  ctx.strokeStyle = "rgba(120,140,100,0.2)";
  [0, 0.25, 0.5, 0.75, 1].forEach((v) => {
    const y = PAD.top + PLOT_H - v * PLOT_H;
    ctx.beginPath();
    ctx.moveTo(PAD.left, y);
    ctx.lineTo(PAD.left + PLOT_W, y);
    ctx.stroke();
    ctx.fillStyle = "#8a9a7e";
    ctx.font      = "10px system-ui";
    ctx.textAlign = "right";
    ctx.fillText(v.toFixed(2), PAD.left - 4, y + 3);
  });
  ctx.setLineDash([]);

  // Line
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth   = 2;
  vals.forEach((v, i) => {
    const x = PAD.left + (i / Math.max(vals.length - 1, 1)) * PLOT_W;
    const y = PAD.top  + PLOT_H - ((v - min) / (max - min)) * PLOT_H;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Dots for last point
  if (vals.length > 0) {
    const lx = PAD.left + PLOT_W;
    const lv = vals[vals.length - 1];
    const ly = PAD.top + PLOT_H - ((lv - min) / (max - min)) * PLOT_H;
    ctx.beginPath();
    ctx.arc(lx, ly, 4, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.fillStyle = "#1e2b1a";
    ctx.font      = "bold 11px system-ui";
    ctx.textAlign = "right";
    ctx.fillText(lv.toFixed(3), lx - 6, ly - 6);
  }

  // X axis labels
  ctx.fillStyle = "#8a9a7e";
  ctx.font      = "10px system-ui";
  ctx.textAlign = "center";
  const rounds  = data.map((d) => d.round);
  [0, Math.floor((rounds.length - 1) / 2), rounds.length - 1].forEach((i) => {
    if (rounds[i] === undefined) return;
    const x = PAD.left + (i / Math.max(rounds.length - 1, 1)) * PLOT_W;
    ctx.fillText(`R${rounds[i]}`, x, PAD.top + PLOT_H + 18);
  });

  // Title
  ctx.fillStyle = "#4a7c59";
  ctx.font      = "bold 12px system-ui";
  ctx.textAlign = "left";
  ctx.fillText(label, PAD.left, PAD.top - 4);
}

export default function MetricsChart({ metrics }) {
  const accRef  = useRef(null);
  const lossRef = useRef(null);

  useEffect(() => {
    drawChart(accRef.current,  metrics, "accuracy", "#4a7c59", "Accuracy vs Rounds");
    drawChart(lossRef.current, metrics, "loss",     "#c0392b", "Loss vs Rounds");
  }, [metrics]);

  if (metrics.length === 0) {
    return (
      <div style={{ color: "#8a9a7e", fontSize: 13, padding: "12px 0" }}>
        ◈ Waiting for first round to complete…
      </div>
    );
  }

  const last = metrics[metrics.length - 1];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Summary row */}
      <div style={{ display: "flex", gap: 24, justifyContent: "center", flexWrap: "wrap" }}>
        <Stat label="Rounds" value={last.round} />
        <Stat label="Accuracy" value={(last.accuracy * 100).toFixed(1) + "%"} color="#4a7c59" />
        <Stat label="Loss"     value={last.loss.toFixed(3)}               color="#c0392b" />
        <Stat label="Last"     value={last.correct ? "✅ Correct" : "❌ Wrong"} />
      </div>

      <canvas ref={accRef}  style={{ borderRadius: 10, background: "rgba(240,235,220,0.6)", display: "block", margin: "0 auto" }} />
      <canvas ref={lossRef} style={{ borderRadius: 10, background: "rgba(240,235,220,0.6)", display: "block", margin: "0 auto" }} />
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: 10, letterSpacing: 2, color: "#8a9a7e", textTransform: "uppercase", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 800, color: color || "#1e2b1a" }}>{value}</div>
    </div>
  );
}