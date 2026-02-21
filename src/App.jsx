import { useState, useEffect, useRef } from "react";
import { collection, addDoc, query, where, onSnapshot } from "firebase/firestore";
import { db } from "./firebase";
import { useRoundTimer } from "./useRoundTimer";
import { v4 as uuidv4 } from "uuid";
import "./App.css";

const USER_ID = uuidv4();

export default function App() {
  const { timeRemaining, currentRound, votingOpen } = useRoundTimer();

  const [hasVoted, setHasVoted] = useState(false);
  const [userVote, setUserVote] = useState(null);
  const [redVotes, setRedVotes] = useState(0);
  const [greenVotes, setGreenVotes] = useState(0);
  const [roundWinner, setRoundWinner] = useState(null);
  const [roundHistory, setRoundHistory] = useState([]);
  const prevRoundRef = useRef(currentRound);

  // Listen silently to votes (not shown to users)
  useEffect(() => {
    const q = query(collection(db, "votes"), where("round", "==", currentRound));
    const unsubscribe = onSnapshot(q, (snapshot) => {
      let red = 0,
        green = 0;
      snapshot.forEach((doc) => {
        if (doc.data().color === "RED") red++;
        else green++;
      });
      setRedVotes(red);
      setGreenVotes(green);
    });
    return () => unsubscribe();
  }, [currentRound]);

  // When voting closes → decide winner
  useEffect(() => {
    if (!votingOpen) {
      if (redVotes > greenVotes) setRoundWinner("RED");
      else if (greenVotes > redVotes) setRoundWinner("GREEN");
      else setRoundWinner("TIE");
    }
  }, [votingOpen, redVotes, greenVotes]);

  // When new round starts → save history
  useEffect(() => {
    if (currentRound !== prevRoundRef.current) {
      const finishedRound = prevRoundRef.current;

      if (roundWinner) {
        setRoundHistory((prev) => {
          const entry = {
            round: finishedRound,
            winner: roundWinner,
          };
          return [entry, ...prev].slice(0, 5);
        });
      }

      setHasVoted(false);
      setUserVote(null);
      setRoundWinner(null);
      prevRoundRef.current = currentRound;
    }
  }, [currentRound]);

  async function castVote(color) {
    if (!votingOpen || hasVoted) return;
    setHasVoted(true);
    setUserVote(color);

    await addDoc(collection(db, "votes"), {
      round: currentRound,
      color: color,
      user_id: USER_ID,
      timestamp: new Date(),
    });
  }

  const timerPct = (timeRemaining / 60) * 100;
  const timerColor =
    timeRemaining > 20
      ? "#4a7c59"
      : timeRemaining > 10
      ? "#c17f3e"
      : "#c0392b";

  return (
    <div className="app">
      <NeuralBg />

      <div className="card main-card">
        <div className="nn-label">◈ NEURAL NETWORK VOTING SYSTEM</div>
        <h1>Project NN</h1>
        <h3>
          Round <span className="round-badge">#{currentRound}</span>
        </h3>

        {/* Timer */}
        <div className="timer-ring-wrap">
          <svg className="timer-ring" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="#e8e0d4" strokeWidth="6" />
            <circle
              cx="60"
              cy="60"
              r="52"
              fill="none"
              stroke={timerColor}
              strokeWidth="6"
              strokeDasharray={`${2 * Math.PI * 52}`}
              strokeDashoffset={`${2 * Math.PI * 52 * (1 - timerPct / 100)}`}
              strokeLinecap="round"
              transform="rotate(-90 60 60)"
              style={{ transition: "stroke-dashoffset 0.5s, stroke 0.5s" }}
            />
          </svg>
          <div className="timer-inner">
            <span className="timer-num">{timeRemaining}</span>
            <span className="timer-unit">sec</span>
          </div>
        </div>

        {/* Status */}
        {hasVoted ? (
          <div
            className={`voted-message ${
              userVote === "RED" ? "voted-red" : "voted-green"
            }`}
          >
            ✅ You voted <strong>{userVote}</strong> this round!
          </div>
        ) : votingOpen ? (
          <p className="info">🗳 Cast your vote below</p>
        ) : (
          <p className="warning">⛔ Voting Closed</p>
        )}

        {/* Winner Announcement */}
        {!votingOpen && roundWinner && (
          <div className={`winner-box winner-${roundWinner.toLowerCase()}`}>
            {roundWinner === "TIE"
              ? "⚖️ It's a TIE!"
              : roundWinner === "RED"
              ? "🔴 RED Wins!"
              : "🟢 GREEN Wins!"}
          </div>
        )}

        {/* Vote Buttons */}
        <div className="button-row">
          <button
            className="vote-btn red-btn"
            onClick={() => castVote("RED")}
            disabled={!votingOpen || hasVoted}
          >
            🔴 RED
          </button>
          <button
            className="vote-btn green-btn"
            onClick={() => castVote("GREEN")}
            disabled={!votingOpen || hasVoted}
          >
            🟢 GREEN
          </button>
        </div>
      </div>

      {/* Past Rounds (Winner Only) */}
      {roundHistory.length > 0 && (
        <div className="card history-card">
          <div className="history-title">◈ Past Round Results</div>
          <div className="history-list">
            {roundHistory.map((r) => (
              <div key={r.round} className="history-row">
                <span>Round #{r.round}</span>
                <span>
                  {r.winner === "TIE"
                    ? "⚖️ TIE"
                    : r.winner === "RED"
                    ? "🔴 RED WON"
                    : "🟢 GREEN WON"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* Neural Background */
function NeuralBg() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    let animId;

    const nodes = [];
    const NODE_COUNT = 28;

    function resize() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < NODE_COUNT; i++) {
      nodes.push({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        r: 2 + Math.random() * 3,
      });
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      nodes.forEach((n) => {
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < 0 || n.x > canvas.width) n.vx *= -1;
        if (n.y < 0 || n.y > canvas.height) n.vy *= -1;
      });

      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 180) {
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(100,120,90,${
              0.12 * (1 - dist / 180)
            })`;
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