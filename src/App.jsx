import { useState, useEffect, useRef } from "react";
import { collection, addDoc, query, where, onSnapshot } from "firebase/firestore";
import { db } from "./firebase";
import { useRoundTimer } from "./useRoundTimer";
import { v4 as uuidv4 } from "uuid";
import "./App.css";

// Generate once per browser session (like st.session_state.user_id)
const USER_ID = uuidv4();

export default function App() {
  // Timer from our custom hook
  const { timeRemaining, currentRound, votingOpen } = useRoundTimer();

  // Local state (= st.session_state)
  const [hasVoted,   setHasVoted]   = useState(false);
  const [userVote,   setUserVote]   = useState(null);
  const [redVotes,   setRedVotes]   = useState(0);
  const [greenVotes, setGreenVotes] = useState(0);
  const prevRoundRef = useRef(currentRound);

  // Reset vote when round changes (like st.session_state.has_voted = False)
  useEffect(() => {
    if (currentRound !== prevRoundRef.current) {
      setHasVoted(false);
      setUserVote(null);
      prevRoundRef.current = currentRound;
    }
  }, [currentRound]);

  // Live vote count from Firestore (real-time, all users)
  // This replaces st.session_state.red_votes / green_votes
  useEffect(() => {
    const q = query(
      collection(db, "votes"),
      where("round", "==", currentRound)
    );

    // onSnapshot = auto-updates whenever Firestore changes
    const unsubscribe = onSnapshot(q, (snapshot) => {
      let red = 0, green = 0;
      snapshot.forEach(doc => {
        if (doc.data().color === "RED")   red++;
        else                                   green++;
      });
      setRedVotes(red);
      setGreenVotes(green);
    });

    return () => unsubscribe(); // cleanup listener on round change
  }, [currentRound]);

  // Cast a vote — like clicking the st.button
  async function castVote(color) {
    if (!votingOpen || hasVoted) return;

    setHasVoted(true);
    setUserVote(color);

    // db.collection("votes").add({...}) — same as your Python code!
    await addDoc(collection(db, "votes"), {
      round:     currentRound,
      color:     color,
      user_id:   USER_ID,
      timestamp: new Date(),
    });
  }

  // ─── What the user sees (= all your st.markdown / st.button calls) ───
  return (
    <div className="app">
      <h1>🎯 Project NN — Voting System</h1>
      <h3>Round #{currentRound}</h3>

      <div className="timer">⏱ {timeRemaining}s</div>

      {/* Status message */}
      {hasVoted ? (
        <div className="voted-message">
          ✅ You voted <strong>{userVote}</strong> this round!
        </div>
      ) : votingOpen ? (
        <p className="info">🗳 Cast your vote!</p>
      ) : (
        <p className="warning">⛔ Voting Closed — Next round soon...</p>
      )}

      {/* Vote buttons */}
      <div className="button-row">
        <button
          className="vote-btn red-btn"
          onClick={/* () => castVote("RED") */() => castVote("RED")}
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

      {/* Stats — like st.metric */}
      <div className="stats">
        <div className="metric">
          <span className="metric-label">Round</span>
          <span className="metric-value">{currentRound}</span>
        </div>
        <div className="metric">
          <span className="metric-label">🔴 Red</span>
          <span className="metric-value">{redVotes}</span>
        </div>
        <div className="metric">
          <span className="metric-label">🟢 Green</span>
          <span className="metric-value">{greenVotes}</span>
        </div>
      </div>
    </div>
  );
}