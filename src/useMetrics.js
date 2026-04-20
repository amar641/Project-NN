// src/useMetrics.js
import { useState, useEffect } from "react";
import { collection, query, orderBy, onSnapshot } from "firebase/firestore";
import { db } from "./firebase";

export function useMetrics() {
  const [metrics, setMetrics] = useState([]);

  useEffect(() => {
    const q = query(
      collection(db, "metrics"),
      orderBy("round", "asc")
      // no limit — we want full history for cumulative accuracy
    );

    const unsub = onSnapshot(q, (snap) => {
      const rows = [];
      snap.forEach((d) => rows.push(d.data()));
      setMetrics(rows);
    });

    return () => unsub();
  }, []);

  return metrics;
}