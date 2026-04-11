// src/useMetrics.js
// Subscribes to the "metrics" Firestore collection and returns
// live accuracy + loss arrays ready for charting.
import { useState, useEffect } from "react";
import { collection, query, orderBy, limit, onSnapshot } from "firebase/firestore";
import { db } from "./firebase";

export function useMetrics(maxPoints = 50) {
  const [metrics, setMetrics] = useState([]);

  useEffect(() => {
    const q = query(
      collection(db, "metrics"),
      orderBy("round", "asc"),
      limit(maxPoints)
    );

    const unsub = onSnapshot(q, (snap) => {
      const rows = [];
      snap.forEach((d) => rows.push(d.data()));
      setMetrics(rows);
    });

    return () => unsub();
  }, [maxPoints]);

  return metrics;   // [{round, accuracy, loss, reward, correct, ts}, ...]
}