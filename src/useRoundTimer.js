// src/useRoundTimer.js
import { useState, useEffect, useRef } from "react";
import { doc, setDoc, onSnapshot, getDoc } from "firebase/firestore";
import { db } from "./firebase";

export const ROUND_DURATION  = 30;  // total seconds
export const HUMAN_CUTOFF    = 10;  // humans stop voting when 10s remain
export const AGENT_CUTOFF    = 5;   // agents done when 5s remain
export const PREDICT_CUTOFF  = 0;   // prediction shown in last 5s (when <=5s remain)

// Phase labels for the frontend
// 0-20s  elapsed (30-10 remaining): VOTING  - humans can vote
// 20-25s elapsed (10-5  remaining): AGENTS  - agents voting, humans locked
// 25-30s elapsed (5-0   remaining): PREDICT - prediction visible, counting down
export function getPhase(timeRemaining) {
  if (timeRemaining > HUMAN_CUTOFF) return "voting";    // >10s left
  if (timeRemaining > AGENT_CUTOFF) return "agents";    // 6-10s left
  return "predict";                                      // 0-5s left
}

const ROUND_DOC = doc(db, "gameState", "currentRound");

async function advanceRound(expectedRound) {
  try {
    const snap = await getDoc(ROUND_DOC);
    if (!snap.exists()) return;
    if (snap.data().round !== expectedRound) return;
    await setDoc(ROUND_DOC, {
      round: expectedRound + 1,
      startedAt: Date.now(),
    });
  } catch (e) {
    console.error("advanceRound error:", e);
  }
}

async function ensureRoundDoc() {
  const snap = await getDoc(ROUND_DOC);
  if (!snap.exists()) {
    await setDoc(ROUND_DOC, { round: 1, startedAt: Date.now() });
  }
}

export function useRoundTimer() {
  const [roundData,      setRoundData]      = useState(null);
  const [timeRemaining,  setTimeRemaining]  = useState(ROUND_DURATION);
  const [phase,          setPhase]          = useState("voting");

  const intervalRef  = useRef(null);
  const advancingRef = useRef(false);

  useEffect(() => {
    ensureRoundDoc();
    const unsubscribe = onSnapshot(ROUND_DOC, (snap) => {
      if (!snap.exists()) return;
      setRoundData(snap.data());
      advancingRef.current = false;
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (!roundData) return;
    if (intervalRef.current) clearInterval(intervalRef.current);

    const { startedAt } = roundData;

    const tick = () => {
      const elapsed   = (Date.now() - startedAt) / 1000;
      const remaining = Math.max(0, ROUND_DURATION - elapsed);
      const floored   = Math.floor(remaining);

      setTimeRemaining(floored);
      setPhase(getPhase(floored));

      if (remaining <= 0 && !advancingRef.current) {
        advancingRef.current = true;
        advanceRound(roundData.round);
      }
    };

    tick();
    intervalRef.current = setInterval(tick, 500); // 500ms for smoother phase transitions

    return () => clearInterval(intervalRef.current);
  }, [roundData]);

  return {
    timeRemaining,
    currentRound: roundData?.round ?? 1,
    // legacy compat - votingOpen = humans can vote
    votingOpen:   phase === "voting",
    phase,        // "voting" | "agents" | "predict"
  };
}