import { useState, useEffect, useRef } from "react";
import { collection, addDoc } from "firebase/firestore";
import { db } from "./firebase";

const ROUND_DURATION = 60;  // seconds
const VOTING_CUTOFF  = 5;   // stop voting 5s before end

export function useRoundTimer() {
  // useState = st.session_state in Streamlit
  const [timeRemaining, setTimeRemaining] = useState(ROUND_DURATION);
  const [currentRound,  setCurrentRound]  = useState(1);
  const [votingOpen,    setVotingOpen]    = useState(true);

  // useRef = a value that persists but doesn't cause re-renders
  const roundStartRef = useRef(Date.now());

  // useEffect runs ONCE when component mounts (like __init__)
  useEffect(() => {
    // setInterval = runs every 500ms (like time.sleep in a loop)
    const interval = setInterval(() => {
      const elapsed   = (Date.now() - roundStartRef.current) / 1000;
      const remaining = Math.max(0, ROUND_DURATION - elapsed);

      setTimeRemaining(Math.ceil(remaining));
      setVotingOpen(remaining > VOTING_CUTOFF);

      // Round ended — advance to next round
      if (remaining <= 0) {
        setCurrentRound(r => r + 1);  // increment round
        roundStartRef.current = Date.now();  // reset timer
        setTimeRemaining(ROUND_DURATION);
        setVotingOpen(true);
      }
    }, 500);

    // Cleanup: stop interval when component unmounts
    return () => clearInterval(interval);
  }, []); // ← empty [] means "run once on load"

  return { timeRemaining, currentRound, votingOpen };
}