//src/App.jsx
import { useState, useEffect, useRef } from "react";
import {
  collection, addDoc, query, where, onSnapshot,
  doc, getDoc, setDoc
} from "firebase/firestore";
import { db } from "./firebase";
import { useRoundTimer, ROUND_DURATION, VOTING_CUTOFF } from "./useRoundTimer";
import { v4 as uuidv4 } from "uuid";
import "./App.css";

// Stable user ID for this browser session (not re-created on re-render)
const USER_ID = (() => {
  let id = sessionStorage.getItem("nn_user_id");
  if (!id) { id = uuidv4(); sessionStorage.setItem("nn_user_id", id); }
  return id;
})();

export default function App() {
  const { timeRemaining, currentRound, votingOpen } = useRoundTimer();

  // ── Voting state ──────────────────────────────────────────────────────────
  const [hasVoted,  setHasVoted]  = useState(false);
  const [userVote,  setUserVote]  = useState(null);
  const [redVotes,  setRedVotes]  = useState(0);
  const [greenVotes,setGreenVotes]= useState(0);

  // ── Round result state ────────────────────────────────────────────────────
  const [roundWinner,  setRoundWinner]  = useState(null);
  const [roundHistory, setRoundHistory] = useState([]);
  const prevRoundRef   = useRef(currentRound);
  const winnerRef      = useRef(null); // stable ref for history capture

  // ── Listen to votes for current round (real-time) ─────────────────────────
  useEffect(() => {
    const q = query(
      collection(db, "votes"),
      where("round", "==", currentRound)
    );
    const unsub = onSnapshot(q, (snap) => {
      let red = 0, green = 0;
      snap.forEach((d) => {
        if (d.data().color === "RED") red++;
        else green++;
      });
      setRedVotes(red);
      setGreenVotes(green);
    });
    return () => unsub();
  }, [currentRound]);

  // ── Determine winner when voting closes ───────────────────────────────────
  useEffect(() => {
    if (!votingOpen) {
      const w = redVotes > greenVotes ? "RED"
              : greenVotes > redVotes ? "GREEN"
              : "TIE";
      setRoundWinner(w);
      winnerRef.current = w;
    }
  }, [votingOpen]); // intentionally NOT depending on vote counts to avoid flicker

  // ── When round advances: save history, reset local state ──────────────────
  useEffect(() => {
    if (currentRound !== prevRoundRef.current) {
      const finished = prevRoundRef.current;
      const winner   = winnerRef.current;

      if (winner) {
        setRoundHistory((prev) =>
          [{ round: finished, winner, red: redVotes, green: greenVotes }, ...prev].slice(0, 5)
        );
      }

      // Reset for new round
      setHasVoted(false);
      setUserVote(null);
      setRoundWinner(null);
      winnerRef.current = null;
      prevRoundRef.current = currentRound;
    }
  }, [currentRound]);

  // ── Cast vote ─────────────────────────────────────────────────────────────
  async function castVote(color) {
    if (!votingOpen || hasVoted) return;
    setHasVoted(true);
    setUserVote(color);
    try {
      await addDoc(collection(db, "votes"), {
        round: currentRound,
        color,
        user_id: USER_ID,
        timestamp: Date.now(),
      });
    } catch (e) {
      // Rollback optimistic update on failure
      setHasVoted(false);
      setUserVote(null);
    }
  }

  // ── Derived display values ────────────────────────────────────────────────
  const timerPct = (timeRemaining / ROUND_DURATION) * 100;
  const timerColor =
    timeRemaining > ROUND_DURATION * 0.67 ? "#4a7c59"
    : timeRemaining > ROUND_DURATION * 0.33 ? "#c17f3e"
    : "#c0392b";

  const circumference = 2 * Math.PI * 52;

  return (
    <div className="app">
      <NeuralBg />

      <div className="card main-card">
        <div className="nn-label">◈ NEURAL NETWORK VOTING SYSTEM</div>
        <h1>Project NN</h1>
        <h3>
          Round <span className="round-badge">#{currentRound}</span>
        </h3>

        {/* ── Timer Ring ── */}
        <div className="timer-ring-wrap">
          <svg className="timer-ring" viewBox="0 0 120 120">
            <circle
              cx="60" cy="60" r="52"
              fill="none" stroke="#e8e0d4" strokeWidth="6"
            />
            <circle
              cx="60" cy="60" r="52"
              fill="none"
              stroke={timerColor}
              strokeWidth="6"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - timerPct / 100)}
              strokeLinecap="round"
              transform="rotate(-90 60 60)"
              style={{ transition: "stroke-dashoffset 0.9s linear, stroke 0.5s" }}
            />
          </svg>
          <div className="timer-inner">
            <span className="timer-num">{timeRemaining}</span>
            <span className="timer-unit">sec</span>
          </div>
        </div>

        {/* ── Status ── */}
        {hasVoted ? (
          <div className={`voted-message ${userVote === "RED" ? "voted-red" : "voted-green"}`}>
            ✅ You voted <strong>{userVote}</strong> this round!
          </div>
        ) : votingOpen ? (
          <p className="info">🗳 Cast your vote below</p>
        ) : (
          <p className="warning">⛔ Voting Closed — counting results…</p>
        )}

        {/* ── Winner Banner ── */}
        {!votingOpen && roundWinner && (
          <div className={`winner-box winner-${roundWinner.toLowerCase()}`}>
            {roundWinner === "TIE"  ? "⚖️ It's a TIE!"
           : roundWinner === "RED"  ? "🔴 RED Wins!"
           :                          "🟢 GREEN Wins!"}
          </div>
        )}

        {/* ── Vote Buttons ── */}
        <div className="button-row">
          <button
            className="vote-btn red-btn"
            onClick={() => castVote("RED")}
            disabled={!votingOpen || hasVoted}
          >
            <span className="btn-icon">🔴</span>
            <span className="btn-label">RED</span>
          </button>
          <button
            className="vote-btn green-btn"
            onClick={() => castVote("GREEN")}
            disabled={!votingOpen || hasVoted}
          >
            <span className="btn-icon">🟢</span>
            <span className="btn-label">GREEN</span>
          </button>
        </div>

        {/* ── Live Vote Count (only show after voting closed) ── */}
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
          </div>
        )}
      </div>

      {/* ── History Card ── */}
      {roundHistory.length > 0 && (
        <div className="card history-card">
          <div className="history-title">◈ Past Round Results</div>
          <div className="history-list">
            {roundHistory.map((r) => (
              <div
                key={r.round}
                className={`history-row winner-${r.winner.toLowerCase()}`}
              >
                <span className="h-round">Round #{r.round}</span>
                <span className="h-votes">
                  🔴 {r.red} — 🟢 {r.green}
                </span>
                <span className={`h-winner badge-${r.winner.toLowerCase()}`}>
                  {r.winner === "TIE"   ? "⚖️ TIE"
                 : r.winner === "RED"   ? "🔴 RED"
                 :                        "🟢 GREEN"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Neural Background Canvas ─────────────────────────────────────────────────
function NeuralBg() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    let animId;
    const nodes = [];
    const NODE_COUNT = 28;

    function resize() {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < NODE_COUNT; i++) {
      nodes.push({
        x:  Math.random() * window.innerWidth,
        y:  Math.random() * window.innerHeight,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        r:  2 + Math.random() * 3,
      });
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      nodes.forEach((n) => {
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < 0 || n.x > canvas.width)  n.vx *= -1;
        if (n.y < 0 || n.y > canvas.height)  n.vy *= -1;
      });
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx   = nodes[i].x - nodes[j].x;
          const dy   = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 180) {
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(100,120,90,${0.12 * (1 - dist / 180)})`;
            ctx.stroke();
          }
        }
      }
      nodes.forEach((n) => {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(80,110,75,0.25)";
        ctx.fill();
      });
      animId = requestAnimationFrame(draw);
    }

    draw();
    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="neural-bg" />;
}