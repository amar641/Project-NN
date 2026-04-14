// src/App.jsx
import { useState, useEffect, useRef } from "react";
import {
  collection, doc, getDoc, setDoc, onSnapshot, query, orderBy, limit
} from "firebase/firestore";
import { db } from "./firebase";
import { useRoundTimer, ROUND_DURATION, HUMAN_CUTOFF, AGENT_CUTOFF } from "./useRoundTimer";
import { useMetrics } from "./useMetrics";
import MetricsChart from "./MetricsChart";
import { v4 as uuidv4 } from "uuid";
import "./App.css";

const USER_ID = (() => {
  let id = sessionStorage.getItem("nn_user_id");
  if (!id) { id = uuidv4(); sessionStorage.setItem("nn_user_id", id); }
  return id;
})();

const EMOTION_OPTIONS = [
  { value: "very_strong", label: "Very Strong" },
  { value: "strong",      label: "Strong" },
  { value: "neutral",     label: "Neutral" },
  { value: "low",         label: "Low" },
  { value: "very_low",    label: "Very Low" },
];
const INFLUENCE_OPTIONS = [
  { value: "yes",     label: "Yes" },
  { value: "neutral", label: "Neutral" },
  { value: "no",      label: "No" },
];

export default function App() {
  const { timeRemaining, currentRound, votingOpen, phase } = useRoundTimer();
  const metrics = useMetrics(100);

  const [hasVoted,         setHasVoted]         = useState(false);
  const [userVote,         setUserVote]         = useState(null);
  const [emotionFeel,      setEmotionFeel]      = useState("neutral");
  const [influenceHistory, setInfluenceHistory] = useState("neutral");
  const [redVotes,         setRedVotes]         = useState(0);
  const [greenVotes,       setGreenVotes]       = useState(0);
  const [voterList,        setVoterList]        = useState([]);
  const [humanCount,       setHumanCount]       = useState(0);
  const [roundWinner,      setRoundWinner]      = useState(null);
  const [prediction,       setPrediction]       = useState(null);
  const [predCorrect,      setPredCorrect]      = useState(null);
  const [roundHistory,     setRoundHistory]     = useState([]);  // last 5 completed rounds

  const prevRoundRef = useRef(currentRound);
  const winnerRef    = useRef(null);
  const redRef       = useRef(0);
  const greenRef     = useRef(0);

  // ── Load last 5 completed rounds on mount ─────────────────────────────
  useEffect(() => {
    if (!currentRound) return;
    const load = async () => {
      const rows = [];
      for (let rnum = Math.max(1, currentRound - 5); rnum < currentRound; rnum++) {
        try {
          const snap = await getDoc(doc(db, "roundResults", String(rnum)));
          if (snap.exists()) {
            const d = snap.data();
            if (d.winner) rows.push({
              round:      rnum,
              winner:     d.winner,
              red:        d.redVotes    || 0,
              green:      d.greenVotes  || 0,
              prediction: d.prediction  || null,
              correct:    d.correct     ?? null,
              accuracy:   d.accuracy    ?? null,
            });
          }
        } catch (_) {}
      }
      rows.sort((a, b) => b.round - a.round);
      setRoundHistory(rows.slice(0, 5));
    };
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Live vote listener ─────────────────────────────────────────────────
  useEffect(() => {
    if (!currentRound) return;
    const unsub = onSnapshot(
      collection(db, "rounds", String(currentRound), "votes"),
      (snap) => {
        let red = 0, green = 0, humans = 0;
        const voters = [];
        snap.forEach((d) => {
          const v = d.data();
          if (v.color === "RED") red++; else green++;
          if (!v.isAgent) humans++;
          voters.push(v);
        });
        voters.sort((a, b) => (!a.isAgent && b.isAgent ? -1 : a.isAgent && !b.isAgent ? 1 : 0));
        setRedVotes(red); setGreenVotes(green);
        setHumanCount(humans); setVoterList(voters);
        redRef.current = red; greenRef.current = green;
      }
    );
    return () => unsub();
  }, [currentRound]);

  // ── Live prediction + result ───────────────────────────────────────────
  useEffect(() => {
    if (!currentRound) return;
    const unsub = onSnapshot(doc(db, "roundResults", String(currentRound)), (snap) => {
      if (!snap.exists()) return;
      const d = snap.data();
      setPrediction(d.prediction || null);
      if (d.winner) {
        setRoundWinner(d.winner);
        winnerRef.current = d.winner;
        setPredCorrect(d.prediction != null ? d.prediction === d.winner : null);
      }
    });
    return () => unsub();
  }, [currentRound]);

  // ── Check if already voted ─────────────────────────────────────────────
  useEffect(() => {
    if (!currentRound) return;
    getDoc(doc(db, "rounds", String(currentRound), "votes", USER_ID)).then((snap) => {
      if (snap.exists()) {
        const d = snap.data();
        setHasVoted(true); setUserVote(d.color);
        setEmotionFeel(d.emotionFeel || "neutral");
        setInfluenceHistory(d.influenceHistory || "neutral");
      } else {
        setHasVoted(false); setUserVote(null);
      }
    });
  }, [currentRound]);

  // ── Round transition ───────────────────────────────────────────────────
  useEffect(() => {
    if (!currentRound || currentRound === prevRoundRef.current) {
      if (prevRoundRef.current == null) prevRoundRef.current = currentRound;
      return;
    }

    const finished = prevRoundRef.current;
    getDoc(doc(db, "roundResults", String(finished))).then((snap) => {
      let winner = winnerRef.current;
      let red    = redRef.current;
      let green  = greenRef.current;
      let prediction_val = null;
      let correct_val    = null;
      let accuracy_val   = null;

      if (snap.exists()) {
        const d = snap.data();
        if (d.winner)     winner         = d.winner;
        if (d.redVotes)   red            = d.redVotes;
        if (d.greenVotes) green          = d.greenVotes;
        prediction_val = d.prediction  || null;
        correct_val    = d.correct     ?? null;
        accuracy_val   = d.accuracy    ?? null;
      }

      if (!winner) winner = red > green ? "RED" : green > red ? "GREEN" : "TIE";

      setRoundHistory((prev) => {
        const entry = { round: finished, winner, red, green,
                        prediction: prediction_val, correct: correct_val, accuracy: accuracy_val };
        return [entry, ...prev.filter(r => r.round !== finished)].slice(0, 5);
      });
    }).catch(() => {
      const winner = winnerRef.current || (redRef.current > greenRef.current ? "RED"
                   : greenRef.current > redRef.current ? "GREEN" : "TIE");
      setRoundHistory((prev) =>
        [{ round: finished, winner, red: redRef.current, green: greenRef.current,
           prediction: null, correct: null, accuracy: null },
         ...prev.filter(r => r.round !== finished)].slice(0, 5)
      );
    });

    // Reset for new round
    setHasVoted(false); setUserVote(null); setRoundWinner(null);
    setPrediction(null); setPredCorrect(null);
    setEmotionFeel("neutral"); setInfluenceHistory("neutral");
    setVoterList([]); setRedVotes(0); setGreenVotes(0); setHumanCount(0);
    winnerRef.current = null;
    prevRoundRef.current = currentRound;
  }, [currentRound]);

  async function castVote(color) {
    if (!votingOpen || hasVoted) return;
    setHasVoted(true); setUserVote(color);
    try {
      await setDoc(doc(db, "rounds", String(currentRound), "votes", USER_ID), {
        userId: USER_ID, color, emotionFeel, influenceHistory,
        isAgent: false, votedAt: Date.now(),
      });
    } catch (e) { setHasVoted(false); setUserVote(null); }
  }

  const timerPct      = (timeRemaining / ROUND_DURATION) * 100;
  const timerColor    = phase === "voting"  ? "#4a7c59"
                      : phase === "agents"  ? "#c17f3e"
                      :                       "#c0392b";
  const circumference = 2 * Math.PI * 52;

  // Phase label for the UI
  const phaseLabel = phase === "voting"  ? { text: "VOTING OPEN",      cls: "phase-voting"  }
                   : phase === "agents"  ? { text: "AGENTS VOTING…",   cls: "phase-agents"  }
                   :                       { text: "COMPUTING MODEL…", cls: "phase-predict" };

  return (
    <div className="app">
      <NeuralBg />

      {/* ── Main voting card ──────────────────────────────────────────── */}
      <div className="card main-card">
        <div className="nn-label">◈ NEURAL NETWORK VOTING SYSTEM</div>
        <h1>Project NN</h1>
        <h3>Round <span className="round-badge">#{currentRound}</span></h3>

        {/* Phase indicator */}
        <div className={`phase-indicator ${phaseLabel.cls}`}>
          {phaseLabel.text}
          <span className="phase-time"> · {timeRemaining}s</span>
        </div>

        {/* ── HMNN Prediction — only visible in "predict" phase ────── */}
        <div className={`prediction-panel ${phase === "predict" || roundWinner ? "pred-visible" : "pred-hidden"}`}>
          <div className="pred-header">HMNN PREDICTION</div>
          {prediction ? (
            <div className={`pred-value-big ${prediction === "RED" ? "pred-red" : "pred-green"}`}>
              {prediction === "RED" ? " RED" : " GREEN"}
              {roundWinner && (
                <span className={`pred-outcome ${predCorrect ? "pred-correct" : "pred-wrong"}`}>
                  {predCorrect ? "CORRECT" : " WRONG"}
                </span>
              )}
            </div>
          ) : (
            <div className="pred-computing">
              {phase === "predict" ? " Computing from last 5 rounds…" : "—"}
            </div>
          )}
        </div>

        {/* Human count */}
        <div className="voter-count">
          👤 <strong>{humanCount}</strong> human{humanCount !== 1 ? "s" : ""} voted
          {phase === "agents" && (
            <span className="agent-fill"> ·  agents voting now…</span>
          )}
          {phase === "voting" && humanCount < 12 && (
            <span className="agent-fill"> · agents fill remaining slots at 10s</span>
          )}
        </div>

        {/* Timer ring */}
        <div className="timer-ring-wrap">
          <svg className="timer-ring" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="#e8e0d4" strokeWidth="6" />
            <circle cx="60" cy="60" r="52" fill="none" stroke={timerColor} strokeWidth="6"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - timerPct / 100)}
              strokeLinecap="round" transform="rotate(-90 60 60)"
              style={{ transition: "stroke-dashoffset 0.9s linear, stroke 0.5s" }} />
          </svg>
          <div className="timer-inner">
            <span className="timer-num">{timeRemaining}</span>
            <span className="timer-unit">sec</span>
          </div>
        </div>

        {/* Dropdowns — disabled once voting closes */}
        <div className="dropdowns-row">
          <div className="dropdown-group">
            <label className="dropdown-label">Emotion Feel</label>
            <select className="dropdown-select" value={emotionFeel}
              onChange={(e) => setEmotionFeel(e.target.value)}
              disabled={hasVoted || !votingOpen}>
              {EMOTION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="dropdown-group">
            <label className="dropdown-label">Influenced by History</label>
            <select className="dropdown-select" value={influenceHistory}
              onChange={(e) => setInfluenceHistory(e.target.value)}
              disabled={hasVoted || !votingOpen}>
              {INFLUENCE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>

        {/* Status message */}
        {hasVoted ? (
          <div className={`voted-message ${userVote === "RED" ? "voted-red" : "voted-green"}`}>
             Voted <strong>{userVote}</strong>
            &nbsp;· Emotion: <strong>{EMOTION_OPTIONS.find(o => o.value === emotionFeel)?.label}</strong>
            &nbsp;· History: <strong>{INFLUENCE_OPTIONS.find(o => o.value === influenceHistory)?.label}</strong>
          </div>
        ) : phase === "voting" ? (
          <p className="info">🗳 Select your options and cast your vote below</p>
        ) : phase === "agents" ? (
          <p className="warning">⛔ Human voting closed — agents are voting…</p>
        ) : (
          <p className="warning">⛔ All voting closed — model is computing…</p>
        )}

        {/* Winner box (after round ends) */}
        {roundWinner && (
          <div className={`winner-box winner-${roundWinner.toLowerCase()}`}>
            {roundWinner === "TIE" ? "⚖️ It's a TIE!"
             : roundWinner === "RED" ? " RED Wins!" : " GREEN Wins!"}
          </div>
        )}

        {/* Vote buttons */}
        <div className="button-row">
          <button className="vote-btn red-btn"
            onClick={() => castVote("RED")} disabled={!votingOpen || hasVoted}>
            <span className="btn-icon"></span>
            <span className="btn-label">RED</span>
          </button>
          <button className="vote-btn green-btn"
            onClick={() => castVote("GREEN")} disabled={!votingOpen || hasVoted}>
            <span className="btn-icon"></span>
            <span className="btn-label">GREEN</span>
          </button>
        </div>

        {/* Vote tally — visible in agents + predict phases or after winner */}
        {(phase !== "voting" || roundWinner) && (redVotes + greenVotes) > 0 && (
          <div className="stats">
            <div className="metric">
              <span className="metric-label">RED</span>
              <span className="metric-value red-text">{redVotes}</span>
            </div>
            <div className="divider-v" />
            <div className="metric">
              <span className="metric-label">GREEN</span>
              <span className="metric-value green-text">{greenVotes}</span>
            </div>
            <div className="divider-v" />
            <div className="metric">
              <span className="metric-label">Total</span>
              <span className="metric-value">{redVotes + greenVotes}/12</span>
            </div>
          </div>
        )}
      </div>

      {/* ── Voter list ────────────────────────────────────────────────── */}
      {phase !== "voting" && voterList.length > 0 && (
        <div className="card voter-list-card">
          <div className="nn-label">◈ VOTES THIS ROUND ({voterList.length}/12)</div>
          <div className="voter-list">
            {voterList.map((v, i) => (
              <div key={v.userId || i} className={`voter-row voter-${v.color?.toLowerCase()}`}>
                <span className="voter-name">{v.isAgent ? "🤖" : "👤"} {v.agentName || "You"}</span>
                <span className={`voter-color badge-${v.color?.toLowerCase()}`}>
                  {v.color === "RED" ? "🔴 RED" : "🟢 GREEN"}
                </span>
                <span className="voter-meta">{v.emotionFeel} · {v.influenceHistory}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Last 5 results: Actual vs Model ──────────────────────────── */}
      {roundHistory.length > 0 && (
        <div className="card history-card">
          <div className="history-title">◈ LAST {roundHistory.length} ROUNDS — ACTUAL vs MODEL</div>
          <div className="results-table">
            <div className="results-header">
              <span>Round</span>
              <span>Votes</span>
              <span>Actual</span>
              <span>Model</span>
              <span>Result</span>
            </div>
            {roundHistory.map((r) => (
              <div key={r.round} className={`results-row winner-${r.winner.toLowerCase()}`}>
                <span className="res-round">#{r.round}</span>
                <span className="res-votes">
                  <span className="red-text">🔴{r.red}</span>
                  <span> — </span>
                  <span className="green-text">🟢{r.green}</span>
                </span>
                <span className={`res-actual badge-${r.winner.toLowerCase()}`}>
                  {r.winner}
                </span>
                <span className={`res-pred ${
                  r.prediction == null ? "pred-none"
                  : r.prediction === "RED" ? "badge-red" : "badge-green"
                }`}>
                  {r.prediction || "—"}
                </span>
                <span className="res-outcome">
                  {r.correct === true  ? "✅" :
                   r.correct === false ? "❌" : "—"}
                </span>
              </div>
            ))}
          </div>

          {/* Running accuracy from last 5 */}
          {roundHistory.some(r => r.correct !== null) && (() => {
            const scored  = roundHistory.filter(r => r.correct !== null);
            const correct = scored.filter(r => r.correct).length;
            const pct     = Math.round((correct / scored.length) * 100);
            return (
              <div className="accuracy-strip">
                Model accuracy (last {scored.length}): &nbsp;
                <strong style={{ color: pct >= 60 ? "#2e7d32" : pct >= 40 ? "#c17f3e" : "#c0392b" }}>
                  {correct}/{scored.length} = {pct}%
                </strong>
              </div>
            );
          })()}
        </div>
      )}

      {/* ── Live model performance chart ──────────────────────────────── */}
      <div className="card metrics-card">
        <div className="nn-label">◈ LIVE MODEL PERFORMANCE</div>
        <MetricsChart metrics={metrics} />
      </div>
    </div>
  );
}

function NeuralBg() {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx    = canvas.getContext("2d");
    let animId;
    const nodes  = [];
    function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
    resize();
    window.addEventListener("resize", resize);
    for (let i = 0; i < 28; i++)
      nodes.push({ x: Math.random()*window.innerWidth, y: Math.random()*window.innerHeight,
        vx: (Math.random()-0.5)*0.4, vy: (Math.random()-0.5)*0.4, r: 2+Math.random()*3 });
    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      nodes.forEach((n) => {
        n.x += n.vx; n.y += n.vy;
        if (n.x < 0 || n.x > canvas.width)  n.vx *= -1;
        if (n.y < 0 || n.y > canvas.height) n.vy *= -1;
      });
      for (let i = 0; i < nodes.length; i++)
        for (let j = i+1; j < nodes.length; j++) {
          const dx = nodes[i].x-nodes[j].x, dy = nodes[i].y-nodes[j].y;
          const dist = Math.sqrt(dx*dx+dy*dy);
          if (dist < 180) {
            ctx.beginPath(); ctx.moveTo(nodes[i].x, nodes[i].y); ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(100,120,90,${0.12*(1-dist/180)})`; ctx.stroke();
          }
        }
      nodes.forEach((n) => { ctx.beginPath(); ctx.arc(n.x,n.y,n.r,0,Math.PI*2); ctx.fillStyle="rgba(80,110,75,0.25)"; ctx.fill(); });
      animId = requestAnimationFrame(draw);
    }
    draw();
    return () => { cancelAnimationFrame(animId); window.removeEventListener("resize", resize); };
  }, []);
  return <canvas ref={canvasRef} className="neural-bg" />;
}