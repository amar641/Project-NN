// src/MetricsChart.jsx
import { useRef, useEffect } from "react";

const W = 480, H = 200;
const PAD = { top: 20, right: 20, bottom: 40, left: 52 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

function buildCumulative(metrics) {
  // metrics: [{round, correct, ...}, ...]
  // Recompute cumulative accuracy and loss from scratch
  // so the graph always reflects full history correctly
  let totalCorrect = 0;
  return metrics.map((m, i) => {
    if (m.correct) totalCorrect++;
    const n = i + 1;
    const cumAcc  = totalCorrect / n;
    const cumLoss = 1 - cumAcc;
    return {
      round:      m.round,
      cumAcc,
      cumLoss,
      correct:    m.correct,
      totalCorrect,
      totalWrong: n - totalCorrect,
      n,
    };
  });
}

function drawTrainingChart(canvas, cumData) {
  if (!canvas || cumData.length === 0) return;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width  = W + "px";
  canvas.style.height = H + "px";
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const n = cumData.length;
  const xOf = (i) => PAD.left + (i / Math.max(n - 1, 1)) * PLOT_W;
  const yOf = (v) => PAD.top + PLOT_H - Math.max(0, Math.min(1, v)) * PLOT_H;

  // ── Correct band (green fill under accuracy curve) ──
  ctx.beginPath();
  ctx.moveTo(xOf(0), yOf(0));
  cumData.forEach((d, i) => ctx.lineTo(xOf(i), yOf(d.cumAcc)));
  ctx.lineTo(xOf(n - 1), yOf(0));
  ctx.closePath();
  ctx.fillStyle = "rgba(59,109,17,0.10)";
  ctx.fill();

  // ── Wrong band (red fill above accuracy to 1.0) ──
  ctx.beginPath();
  ctx.moveTo(xOf(0), yOf(1));
  cumData.forEach((d, i) => ctx.lineTo(xOf(i), yOf(d.cumAcc)));
  ctx.lineTo(xOf(n - 1), yOf(1));
  ctx.closePath();
  ctx.fillStyle = "rgba(163,45,45,0.08)";
  ctx.fill();

  // ── Y gridlines ──
  ctx.setLineDash([3, 5]);
  ctx.strokeStyle = "rgba(120,140,100,0.2)";
  ctx.lineWidth = 1;
  [0, 0.25, 0.5, 0.75, 1].forEach((v) => {
    const y = yOf(v);
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + PLOT_W, y); ctx.stroke();
    ctx.fillStyle = "#8a9a7e";
    ctx.font = "10px system-ui";
    ctx.textAlign = "right";
    ctx.fillText((v * 100).toFixed(0) + "%", PAD.left - 5, y + 3);
  });
  ctx.setLineDash([]);

  // ── Axes ──
  ctx.strokeStyle = "rgba(120,140,100,0.35)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD.left, PAD.top);
  ctx.lineTo(PAD.left, PAD.top + PLOT_H);
  ctx.lineTo(PAD.left + PLOT_W, PAD.top + PLOT_H);
  ctx.stroke();

  // ── 50% baseline (random chance reference) ──
  ctx.setLineDash([6, 4]);
  ctx.strokeStyle = "rgba(120,120,80,0.4)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD.left, yOf(0.5));
  ctx.lineTo(PAD.left + PLOT_W, yOf(0.5));
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "rgba(120,120,80,0.55)";
  ctx.font = "9px system-ui";
  ctx.textAlign = "left";
  ctx.fillText("50%", PAD.left + 3, yOf(0.5) - 3);

  // ── Loss curve (dashed red) ──
  ctx.beginPath();
  ctx.strokeStyle = "#A32D2D";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([5, 4]);
  cumData.forEach((d, i) => {
    i === 0 ? ctx.moveTo(xOf(i), yOf(d.cumLoss)) : ctx.lineTo(xOf(i), yOf(d.cumLoss));
  });
  ctx.stroke();
  ctx.setLineDash([]);

  // ── Accuracy curve (solid green) ──
  ctx.beginPath();
  ctx.strokeStyle = "#3B6D11";
  ctx.lineWidth = 2;
  cumData.forEach((d, i) => {
    i === 0 ? ctx.moveTo(xOf(i), yOf(d.cumAcc)) : ctx.lineTo(xOf(i), yOf(d.cumAcc));
  });
  ctx.stroke();

  // ── Last-point dot + label ──
  const last = cumData[cumData.length - 1];
  const lx = xOf(n - 1);
  const ly = yOf(last.cumAcc);
  ctx.beginPath(); ctx.arc(lx, ly, 4, 0, Math.PI * 2);
  ctx.fillStyle = "#3B6D11"; ctx.fill();
  ctx.fillStyle = "#1e2b1a";
  ctx.font = "bold 11px system-ui";
  ctx.textAlign = "right";
  ctx.fillText((last.cumAcc * 100).toFixed(1) + "%", lx - 7, ly - 6);

  // ── X axis round labels ──
  ctx.fillStyle = "#8a9a7e";
  ctx.font = "10px system-ui";
  ctx.textAlign = "center";
  const step = Math.ceil(n / 5);
  for (let i = 0; i < n; i += step) {
    ctx.fillText(`R${cumData[i].round}`, xOf(i), PAD.top + PLOT_H + 16);
  }
  ctx.fillText(`R${last.round}`, xOf(n - 1), PAD.top + PLOT_H + 16);
}

export default function MetricsChart({ metrics }) {
  const canvasRef = useRef(null);
  const cumData   = buildCumulative(metrics);

  useEffect(() => {
    drawTrainingChart(canvasRef.current, cumData);
  }, [metrics]);

  if (metrics.length === 0) {
    return (
      <div style={{ color: "#8a9a7e", fontSize: 13, padding: "12px 0" }}>
        ◈ Waiting for first round to complete…
      </div>
    );
  }

  const last = cumData[cumData.length - 1];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Summary stats */}
      <div style={{ display: "flex", gap: 20, justifyContent: "center", flexWrap: "wrap" }}>
        <Stat label="Rounds"   value={last.n} />
        <Stat label="Correct"  value={last.totalCorrect} color="#3B6D11" />
        <Stat label="Wrong"    value={last.totalWrong}   color="#A32D2D" />
        <Stat label="Accuracy" value={(last.cumAcc  * 100).toFixed(1) + "%"} color="#3B6D11" />
        <Stat label="Loss"     value={last.cumLoss.toFixed(3)}               color="#A32D2D" />
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 20, justifyContent: "center", fontSize: 11, color: "#6b7a5e" }}>
        <span>
          <span style={{ display: "inline-block", width: 16, height: 2, background: "#3B6D11", verticalAlign: "middle", marginRight: 4 }} />
          Cumulative accuracy
        </span>
        <span>
          <span style={{ display: "inline-block", width: 16, height: 2, borderTop: "2px dashed #A32D2D", verticalAlign: "middle", marginRight: 4 }} />
          Cumulative loss
        </span>
        <span style={{ color: "#999" }}>— — 50% baseline</span>
      </div>

      <canvas
        ref={canvasRef}
        style={{ borderRadius: 10, background: "rgba(240,235,220,0.6)", display: "block", margin: "0 auto" }}
      />
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