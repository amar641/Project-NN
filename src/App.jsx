// src/App.jsx  (updated – adds prediction banner + metrics card)
import { useState, useEffect, useRef } from "react";
import {
  collection, doc, getDoc, setDoc, onSnapshot, query, orderBy, limit
} from "firebase/firestore";
import { db } from "./firebase";
import { useRoundTimer, ROUND_DURATION } from "./useRoundTimer";
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

// ─── API base URL – change to your backend URL in production ─────────────────
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function App() {
  const { timeRemaining, currentRound, votingOpen } = useRoundTimer();
  const metrics = useMetrics(100);

  const [hasVoted,         setHasVoted]         = useState(false);
  const [userVote,         setUserVote]         = useState(null);
  const [emotionFeel,      setEmotionFeel]      = useState("neutral");
  const [influenceHistory, setInfluenceHistory] = useState("neutral");
  const [redVotes,         setRedVotes]         = useState(0);
  const [greenVotes,       setGreenVotes]       = useState(0);
  const [roundWinner,      setRoundWinner]      = useState(null);
  const [roundHistory,     setRoundHistory]     = useState([]);
  const [prediction,       setPrediction]       = useState(null);
  const [humanCount,       setHumanCount]       = useState(0);
  const [voterList,        setVoterList]        = useState([]);

  const prevRoundRef = useRef(currentRound);
  const winnerRef    = useRef(null);

  // Live vote count
  useEffect(() => {
    if (!currentRound) return;
    const votesCol = collection(db, "rounds", String(currentRound), "votes");
    const unsub = onSnapshot(query(votesCol), (snap) => {
      let red = 0, green = 0, humans = 0;
      snap.forEach((d) => {
        const data = d.data();
        if (data.color === "RED") red++; else green++;
        if (!data.isAgent) humans++;
      });
      setRedVotes(red);
      setGreenVotes(green);
      setHumanCount(humans);
      // Build sorted voter list: humans first, then agents
      const allVoters = [];
      snap.forEach((d) => allVoters.push(d.data()));
      allVoters.sort((a, b) => (a.isAgent ? 1 : -1) - (b.isAgent ? 1 : -1));
      setVoterList(allVoters);
    });
    return () => unsub();
  }, [currentRound]);

  // Load prediction for current round
  useEffect(() => {
    if (!currentRound) return;
    const ref = doc(db, "roundResults", String(currentRound));
    const unsub = onSnapshot(ref, (snap) => {
      if (snap.exists()) {
        const d = snap.data();
        setPrediction(d.prediction || null);
        if (d.winner) setRoundWinner(d.winner);
      }
    });
    return () => unsub();
  }, [currentRound]);

  // Check if already voted
  useEffect(() => {
    if (!currentRound) return;
    const voteDoc = doc(db, "rounds", String(currentRound), "votes", USER_ID);
    getDoc(voteDoc).then((snap) => {
      if (snap.exists()) {
        const d = snap.data();
        setHasVoted(true);
        setUserVote(d.color);
        setEmotionFeel(d.emotionFeel || "neutral");
        setInfluenceHistory(d.influenceHistory || "neutral");
      } else {
        setHasVoted(false);
        setUserVote(null);
      }
    });
  }, [currentRound]);

  // Voting closed
  useEffect(() => {
    if (!votingOpen) {
      const w = redVotes > greenVotes ? "RED" : greenVotes > redVotes ? "GREEN" : "TIE";
      winnerRef.current = w;
    }
  }, [votingOpen]);

  // Round transition
  useEffect(() => {
    if (currentRound !== prevRoundRef.current) {
      const finished = prevRoundRef.current;
      const winner   = winnerRef.current;
      if (winner) {
        setRoundHistory((prev) =>
          [{ round: finished, winner, red: redVotes, green: greenVotes }, ...prev].slice(0, 5)
        );
      }
      setHasVoted(false); setUserVote(null); setRoundWinner(null);
      setEmotionFeel("neutral"); setInfluenceHistory("neutral");
      setPrediction(null);
      setVoterList([]);
      winnerRef.current = null;
      prevRoundRef.current = currentRound;
    }
  }, [currentRound]);

  async function castVote(color) {
    if (!votingOpen || hasVoted) return;
    setHasVoted(true); setUserVote(color);
    try {
      // Write directly to Firestore (backend reads it)
      const voteDoc = doc(db, "rounds", String(currentRound), "votes", USER_ID);
      await setDoc(voteDoc, {
        userId: USER_ID, color,
        emotionFeel, influenceHistory,
        isAgent: false,
        votedAt: Date.now(),
      });
    } catch (e) {
      setHasVoted(false); setUserVote(null);
    }
  }

  const timerPct      = (timeRemaining / ROUND_DURATION) * 100;
  const timerColor    = timeRemaining > ROUND_DURATION * 0.67 ? "#4a7c59"
                      : timeRemaining > ROUND_DURATION * 0.33 ? "#c17f3e" : "#c0392b";
  const circumference = 2 * Math.PI * 52;

  return (
    <div className="app">
      <NeuralBg />

      {/* ── Main voting card ─────────────────────────────────────── */}
      <div className="card main-card">
        <div className="nn-label">◈ NEURAL NETWORK VOTING SYSTEM</div>
        <h1>Project NN</h1>
        <h3>Round <span className="round-badge">#{currentRound}</span></h3>

        {/* Prediction banner */}
        {prediction && (
          <div className={`prediction-banner prediction-${prediction.toLowerCase()}`}>
            🧠 HMNN Predicts: <strong>{prediction}</strong>
            {roundWinner && (
              <span className="prediction-result">
                &nbsp;— Actual: <strong>{roundWinner}</strong>
                {prediction === roundWinner ? " ✅" : " ❌"}
              </span>
            )}
          </div>
        )}

        {/* Human voter count */}
        <div className="voter-count">
          👤 <strong>{humanCount}</strong> human{humanCount !== 1 ? "s" : ""} voted
          {humanCount < 12 && votingOpen && (
            <span className="agent-fill"> · {12 - humanCount} agent slots available</span>
          )}
        </div>

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

        <div className="dropdowns-row">
          <div className="dropdown-group">
            <label className="dropdown-label">Emotion Feel</label>
            <select className="dropdown-select" value={emotionFeel}
              onChange={(e) => setEmotionFeel(e.target.value)} disabled={hasVoted || !votingOpen}>
              {EMOTION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="dropdown-group">
            <label className="dropdown-label">Influence from History</label>
            <select className="dropdown-select" value={influenceHistory}
              onChange={(e) => setInfluenceHistory(e.target.value)} disabled={hasVoted || !votingOpen}>
              {INFLUENCE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>

        {hasVoted ? (
          <div className={`voted-message ${userVote === "RED" ? "voted-red" : "voted-green"}`}>
            ✅ Voted <strong>{userVote}</strong> · Emotion: <strong>{EMOTION_OPTIONS.find(o => o.value === emotionFeel)?.label}</strong> · History: <strong>{INFLUENCE_OPTIONS.find(o => o.value === influenceHistory)?.label}</strong>
          </div>
        ) : votingOpen ? (
          <p className="info">🗳 Select your options and cast your vote</p>
        ) : (
          <p className="warning">⛔ Voting Closed — counting results…</p>
        )}

        {!votingOpen && roundWinner && (
          <div className={`winner-box winner-${roundWinner.toLowerCase()}`}>
            {roundWinner === "TIE" ? "⚖️ It's a TIE!" : roundWinner === "RED" ? "🔴 RED Wins!" : "🟢 GREEN Wins!"}
          </div>
        )}

        <div className="button-row">
          <button className="vote-btn red-btn" onClick={() => castVote("RED")} disabled={!votingOpen || hasVoted}>
            <span className="btn-icon">🔴</span>
            <span className="btn-label">RED</span>
          </button>
          <button className="vote-btn green-btn" onClick={() => castVote("GREEN")} disabled={!votingOpen || hasVoted}>
            <span className="btn-icon">🟢</span>
            <span className="btn-label">GREEN</span>
          </button>
        </div>

        {!votingOpen && (
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

      {/* ── Voter list after round ends ───────────────────────────── */}
      {!votingOpen && voterList.length > 0 && (
        <div className="card voter-list-card">
          <div className="nn-label">◈ ALL VOTES THIS ROUND ({voterList.length}/12)</div>
          <div className="voter-list">
            {voterList.map((v, i) => (
              <div key={v.userId || i} className={`voter-row voter-${v.color?.toLowerCase()}`}>
                <span className="voter-name">
                  {v.isAgent ? "🤖" : "👤"} {v.agentName || "You"}
                </span>
                <span className={`voter-color badge-${v.color?.toLowerCase()}`}>
                  {v.color === "RED" ? "🔴 RED" : "🟢 GREEN"}
                </span>
                <span className="voter-meta">
                  {v.emotionFeel} · {v.influenceHistory}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Live metrics chart card ───────────────────────────────── */}
      <div className="card metrics-card">
        <div className="nn-label">◈ LIVE MODEL PERFORMANCE</div>
        <MetricsChart metrics={metrics} />
      </div>

      {/* ── Round history ────────────────────────────────────────── */}
      {roundHistory.length > 0 && (
        <div className="card history-card">
          <div className="history-title">◈ Past Round Results</div>
          <div className="history-list">
            {roundHistory.map((r) => (
              <div key={r.round} className={`history-row winner-${r.winner.toLowerCase()}`}>
                <span className="h-round">Round #{r.round}</span>
                <span className="h-votes">🔴 {r.red} — 🟢 {r.green}</span>
                <span className={`h-winner badge-${r.winner.toLowerCase()}`}>
                  {r.winner === "TIE" ? "⚖️ TIE" : r.winner === "RED" ? "🔴 RED" : "🟢 GREEN"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function NeuralBg() {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    let animId;
    const nodes = [];
    function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
    resize();
    window.addEventListener("resize", resize);
    for (let i = 0; i < 28; i++) {
      nodes.push({ x: Math.random()*window.innerWidth, y: Math.random()*window.innerHeight,
        vx: (Math.random()-0.5)*0.4, vy: (Math.random()-0.5)*0.4, r: 2+Math.random()*3 });
    }
    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      nodes.forEach((n) => {
        n.x += n.vx; n.y += n.vy;
        if (n.x < 0 || n.x > canvas.width) n.vx *= -1;
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