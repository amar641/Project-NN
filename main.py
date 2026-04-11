"""
main.py  — place in project root (same folder as rl_model.py, round_manager.py)
Run with:  uvicorn main:app --host 0.0.0.0 --port 8000
"""

import os
import sys
import asyncio
from contextlib import asynccontextmanager

# Ensure project root is on the path (needed on Windows)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, firestore as fs

# ── Init Firebase ─────────────────────────────────────────────────────────────
FIREBASE_CRED = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase.json")
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CRED)
    firebase_admin.initialize_app(cred)
db = fs.client()

# ── Background round manager task ────────────────────────────────────────────
_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _manager
    from round_manager import RoundManager

    _manager = RoundManager()

    snap = db.collection("gameState").document("currentRound").get()
    start = snap.to_dict().get("round", 1) if snap.exists else 1

    asyncio.create_task(_manager.run(start_round=start))
    yield
    if _manager:
        _manager.model.save_rl("rl_weights.pkl")


app = FastAPI(title="Project NN API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class VoteRequest(BaseModel):
    userId:           str
    roundNum:         int
    color:            str
    emotionFeel:      str
    influenceHistory: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/vote")
def cast_vote(req: VoteRequest):
    if req.color not in ("RED", "GREEN"):
        raise HTTPException(400, "color must be RED or GREEN")

    import time
    doc_ref = (
        db.collection("rounds")
          .document(str(req.roundNum))
          .collection("votes")
          .document(req.userId)
    )
    if doc_ref.get().exists:
        raise HTTPException(409, "Already voted this round")

    doc_ref.set({
        "userId":           req.userId,
        "color":            req.color,
        "emotionFeel":      req.emotionFeel,
        "influenceHistory": req.influenceHistory,
        "isAgent":          False,
        "votedAt":          int(time.time() * 1000),
    })
    return {"status": "ok"}


@app.get("/metrics")
def get_metrics(limit: int = 100):
    docs = (
        db.collection("metrics")
          .order_by("round", direction=fs.Query.DESCENDING)
          .limit(limit)
          .stream()
    )
    rows = sorted([d.to_dict() for d in docs], key=lambda x: x["round"])
    return {"metrics": rows}


@app.get("/prediction/{round_num}")
def get_prediction(round_num: int):
    snap = db.collection("roundResults").document(str(round_num)).get()
    if not snap.exists:
        raise HTTPException(404, "Round not found")
    d = snap.to_dict()
    return {
        "round":      round_num,
        "prediction": d.get("prediction"),
        "winner":     d.get("winner"),
        "correct":    d.get("correct"),
        "accuracy":   d.get("accuracy"),
        "loss":       d.get("loss"),
        "status":     d.get("status"),
    }


@app.get("/results")
def get_results(limit: int = 20):
    docs = (
        db.collection("roundResults")
          .where("status", "==", "done")
          .order_by("round", direction=fs.Query.DESCENDING)
          .limit(limit)
          .stream()
    )
    rows = sorted([d.to_dict() for d in docs], key=lambda x: x["round"])
    return {"results": rows}