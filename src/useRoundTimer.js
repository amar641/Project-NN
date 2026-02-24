// src/useRoundTimer.js
import { useState, useEffect, useRef, useCallback } from "react";
import { doc, setDoc, onSnapshot, getDoc } from "firebase/firestore";
import { db } from "./firebase";

export const ROUND_DURATION = 30; // seconds per round
export const VOTING_CUTOFF = 5;   // stop voting this many seconds before end

const ROUND_DOC = doc(db, "gameState", "currentRound");

// ─── Helper: write new round to Firestore (only if still on old round) ───────
async function advanceRound(expectedRound) {
  try {
    // Read first to avoid overwriting a round already advanced by another user
    const snap = await getDoc(ROUND_DOC);
    if (!snap.exists()) return;
    if (snap.data().round !== expectedRound) return; // already advanced
    await setDoc(ROUND_DOC, {
      round: expectedRound + 1,
      startedAt: Date.now(),
    });
  } catch (e) {
    console.error("advanceRound error:", e);
  }
}

// ─── Initialize Firestore round doc if it doesn't exist ──────────────────────
async function ensureRoundDoc() {
  const snap = await getDoc(ROUND_DOC);
  if (!snap.exists()) {
    await setDoc(ROUND_DOC, { round: 1, startedAt: Date.now() });
  }
}

export function useRoundTimer() {
  // roundData = what's in Firestore (source of truth)
  const [roundData, setRoundData] = useState(null);

  // Derived local timer state (updated every second via setInterval)
  const [timeRemaining, setTimeRemaining] = useState(ROUND_DURATION);
  const [votingOpen, setVotingOpen]       = useState(true);

  // Refs to avoid stale closures in intervals
  const intervalRef      = useRef(null);
  const advancingRef     = useRef(false);   // prevents multiple advance() calls

  // ── Step 1: Init Firestore doc, then subscribe ────────────────────────────
  useEffect(() => {
    ensureRoundDoc();

    const unsubscribe = onSnapshot(ROUND_DOC, (snap) => {
      if (!snap.exists()) return;
      const data = snap.data();
      setRoundData(data);         // triggers Step 2 below
      advancingRef.current = false; // new round confirmed → allow future advance
    });

    return () => unsubscribe();
  }, []);

  // ── Step 2: When roundData changes, (re)start the local tick interval ─────
  useEffect(() => {
    if (!roundData) return;

    // Clear any existing interval before starting a new one
    if (intervalRef.current) clearInterval(intervalRef.current);

    const { startedAt } = roundData;

    // Tick immediately once, then every second
    const tick = () => {
      const elapsed   = (Date.now() - startedAt) / 1000;
      const remaining = Math.max(0, ROUND_DURATION - elapsed);

      setTimeRemaining(Math.floor(remaining)); // floor = stable, no flicker
      setVotingOpen(remaining > VOTING_CUTOFF);

      // Only one user should advance the round
      if (remaining <= 0 && !advancingRef.current) {
        advancingRef.current = true;
        advanceRound(roundData.round);
      }
    };

    tick(); // run immediately to avoid 1-second blank
    intervalRef.current = setInterval(tick, 1000); // every 1s is enough

    return () => clearInterval(intervalRef.current);
  }, [roundData]); // only re-run when Firestore sends a new round

  return {
    timeRemaining,
    currentRound: roundData?.round ?? 1,
    votingOpen,
  };
}