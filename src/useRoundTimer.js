// src/useRoundTimer.js
import { useState, useEffect, useRef } from "react";
import { doc, onSnapshot, getDoc, setDoc } from "firebase/firestore";
import { db } from "./firebase";

export const ROUND_DURATION  = 30;
export const HUMAN_CUTOFF    = 10;
export const AGENT_CUTOFF    = 5;

// Phase logic
export function getPhase(timeRemaining) {
  if (timeRemaining > HUMAN_CUTOFF) return "voting";
  if (timeRemaining > AGENT_CUTOFF) return "agents";
  return "predict";
}

const ROUND_DOC = doc(db, "gameState", "currentRound");

async function ensureRoundDoc() {
  const snap = await getDoc(ROUND_DOC);
  if (!snap.exists()) {
    await setDoc(ROUND_DOC, {
      round: 1,
      startedAt: Date.now(),
    });
  }
}

export function useRoundTimer() {
  const [roundData, setRoundData] = useState(null);
  const [timeRemaining, setTimeRemaining] = useState(ROUND_DURATION);
  const [phase, setPhase] = useState("voting");

  const intervalRef = useRef(null);

  useEffect(() => {
    ensureRoundDoc();

    const unsubscribe = onSnapshot(ROUND_DOC, (snap) => {
      if (!snap.exists()) return;
      setRoundData(snap.data());
    });

    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (!roundData) return;

    if (intervalRef.current) clearInterval(intervalRef.current);

    const { startedAt } = roundData;

    const tick = () => {
      const elapsed = (Date.now() - startedAt) / 1000;
      const remaining = Math.max(0, ROUND_DURATION - elapsed);
      const floored = Math.floor(remaining);

      setTimeRemaining(floored);
      setPhase(getPhase(floored));
    };

    tick();
    intervalRef.current = setInterval(tick, 500);

    return () => clearInterval(intervalRef.current);
  }, [roundData]);

  return {
    timeRemaining,
    currentRound: roundData?.round ?? 1,
    votingOpen: phase === "voting",
    phase,
  };
}