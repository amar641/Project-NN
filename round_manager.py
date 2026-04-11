"""
round_manager.py
Orchestrates each voting round:
  1. Make HMNN prediction
  2. Wait VOTE_WINDOW seconds for human votes
  3. Fill remaining slots with AI agents (OpenAI or fallback)
  4. Write ALL 12 votes to Firestore
  5. Tally, update RL, write results
  6. Advance round counter
"""

import asyncio
import random
import time
import json
import os

import firebase_admin
from firebase_admin import credentials, firestore

from rl_model import RLModel, encode_vote

try:
    from openai import AsyncOpenAI
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False

# ─── Config ───────────────────────────────────────────────────────────────────
ROUND_DURATION = 30
VOTE_WINDOW    = 25
TOTAL_VOTES    = 12
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FIREBASE_CRED  = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccount.json")

EMOTION_OPTIONS   = ["very_low", "low", "neutral", "strong", "very_strong"]
INFLUENCE_OPTIONS = ["no", "neutral", "yes"]

# ─── Agents ───────────────────────────────────────────────────────────────────
AGENTS = [
    {"id": "agent_001", "name": "Aria",   "personality": "Optimistic and trend-following. You love momentum and strong consensus.",          "emotion_bias": "very_strong", "history_bias": "yes",     "contrarian": False},
    {"id": "agent_002", "name": "Brutus", "personality": "Stubborn contrarian. You always bet against the recent winner.",                   "emotion_bias": "low",         "history_bias": "no",      "contrarian": True},
    {"id": "agent_003", "name": "Cleo",   "personality": "Analytical and cautious. You study history carefully before deciding.",            "emotion_bias": "neutral",     "history_bias": "yes",     "contrarian": False},
    {"id": "agent_004", "name": "Drake",  "personality": "Momentum trader. You ride winning streaks hard.",                                  "emotion_bias": "strong",      "history_bias": "yes",     "contrarian": False},
    {"id": "agent_005", "name": "Elsa",   "personality": "Pure gut instinct. You ignore all history and vote randomly.",                     "emotion_bias": "very_low",    "history_bias": "no",      "contrarian": False},
    {"id": "agent_006", "name": "Felix",  "personality": "Mean-reversion believer. You think streaks always end.",                           "emotion_bias": "neutral",     "history_bias": "yes",     "contrarian": True},
    {"id": "agent_007", "name": "Gina",   "personality": "Emotional and impulsive. Recent losses make you swing hard the other way.",        "emotion_bias": "very_strong", "history_bias": "neutral", "contrarian": False},
    {"id": "agent_008", "name": "Hiro",   "personality": "Disciplined systems voter. You follow a strict pattern based on round numbers.",   "emotion_bias": "low",         "history_bias": "yes",     "contrarian": False},
    {"id": "agent_009", "name": "Iris",   "personality": "Social mimic. You follow whatever the crowd seems to be doing.",                   "emotion_bias": "strong",      "history_bias": "yes",     "contrarian": False},
    {"id": "agent_010", "name": "Jules",  "personality": "Pessimist. You have a strong bias toward RED as a danger signal.",                 "emotion_bias": "strong",      "history_bias": "neutral", "contrarian": False},
    {"id": "agent_011", "name": "Kai",    "personality": "Balanced philosopher. You weigh both sides carefully every round.",                "emotion_bias": "neutral",     "history_bias": "neutral", "contrarian": False},
    {"id": "agent_012", "name": "Luna",   "personality": "Superstitious. You see patterns in noise and act on lucky or unlucky streaks.",    "emotion_bias": "very_strong", "history_bias": "yes",     "contrarian": False},
]

# ─── Firebase ─────────────────────────────────────────────────────────────────
def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CRED)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ─── Agent decisions ──────────────────────────────────────────────────────────
async def _agent_openai(agent: dict, history: list[dict]) -> dict:
    client   = AsyncOpenAI(api_key=OPENAI_API_KEY)
    hist_str = json.dumps(history[-5:]) if history else "[]"
    prompt = (
        f"You are {agent['name']}. {agent['personality']}\n"
        f"Last 5 rounds: {hist_str}\n\n"
        "Vote RED or GREEN. Also rate emotional intensity and history influence.\n"
        "Respond ONLY with valid JSON, no extra text:\n"
        '{"color":"RED","emotionFeel":"neutral","influenceHistory":"yes"}\n'
        "emotionFeel options: very_low, low, neutral, strong, very_strong\n"
        "influenceHistory options: no, neutral, yes"
    )
    try:
        res = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.85,
        )
        raw  = res.choices[0].message.content.strip()
        raw  = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        if data.get("color") not in ("RED", "GREEN"):
            raise ValueError("bad color")
        if data.get("emotionFeel") not in EMOTION_OPTIONS:
            data["emotionFeel"] = agent["emotion_bias"]
        if data.get("influenceHistory") not in INFLUENCE_OPTIONS:
            data["influenceHistory"] = agent["history_bias"]
        return data
    except Exception as e:
        print(f"  [OpenAI fallback] {agent['name']}: {e}")
        return _agent_fallback(agent, history)

def _agent_fallback(agent: dict, history: list[dict]) -> dict:
    last_winner = history[-1]["winner"] if history else None
    if agent["contrarian"] and last_winner:
        color = "RED" if last_winner == "GREEN" else "GREEN"
    else:
        color = random.choice(["RED", "GREEN"])
    return {
        "color":            color,
        "emotionFeel":      agent["emotion_bias"],
        "influenceHistory": agent["history_bias"],
    }

async def get_agent_decision(agent: dict, history: list[dict]) -> dict:
    if _HAS_OPENAI and OPENAI_API_KEY:
        return await _agent_openai(agent, history)
    return _agent_fallback(agent, history)

# ─── Round Manager ────────────────────────────────────────────────────────────
class RoundManager:

    def __init__(self):
        self.db           = init_firebase()
        self.model        = RLModel("HMNN.pkl")
        self.model.load_rl("rl_weights.pkl")
        self.round_history: list[dict] = []
        self.window:        list[dict] = []

    async def bootstrap(self):
        snap = self.db.collection("gameState").document("currentRound").get()
        if not snap.exists:
            return
        current = snap.to_dict().get("round", 1)
        for rnum in range(max(1, current - 5), current):
            try:
                rs = self.db.collection("roundResults").document(str(rnum)).get()
                if rs.exists:
                    d = rs.to_dict()
                    self.round_history.append({
                        "round":  rnum,
                        "green":  d.get("greenVotes", 0),
                        "red":    d.get("redVotes", 0),
                        "winner": d.get("winner", "RED"),
                    })
            except Exception:
                pass

    async def run_round(self, round_num: int):
        print(f"\n[RoundManager] ── Round {round_num} ──")

        # 1. Predict before voting starts
        prediction = self.model.predict(self.window, self.round_history)
        self._write_prediction(round_num, prediction)
        print(f"  Prediction: {prediction}")

        # 2. Wait for human votes
        await asyncio.sleep(VOTE_WINDOW)

        # 3. Read human votes (no .where() filter — read all then filter in Python)
        human_votes = self._read_human_votes(round_num)
        print(f"  Human votes: {len(human_votes)}")

        # 4. Fill remaining with agents
        n_needed   = max(0, TOTAL_VOTES - len(human_votes))
        agent_pool = random.sample(AGENTS, n_needed) if n_needed else []
        decisions  = await asyncio.gather(*[
            get_agent_decision(a, self.round_history) for a in agent_pool
        ])

        # 5. Build agent vote dicts
        agent_votes = [
            {
                "userId":           a["id"],
                "agentName":        a["name"],
                "color":            d["color"],
                "emotionFeel":      d["emotionFeel"],
                "influenceHistory": d["influenceHistory"],
                "isAgent":          True,
                "votedAt":          int(time.time() * 1000),
            }
            for a, d in zip(agent_pool, decisions)
        ]

        # 6. Write all agent votes to Firestore
        for v in agent_votes:
            self._write_vote(round_num, v["userId"], v)
        print(f"  Agent votes written: {len(agent_votes)}")

        # 7. Tally
        all_votes = human_votes + agent_votes
        red   = sum(1 for v in all_votes if v["color"] == "RED")
        green = sum(1 for v in all_votes if v["color"] == "GREEN")
        winner = "RED" if red > green else "GREEN"
        print(f"  Total={len(all_votes)} RED={red} GREEN={green} → {winner}")

        # 8. HMNN voter matrix
        voter_matrix = {
            "votes": [
                encode_vote(v["color"], v["emotionFeel"], v["influenceHistory"])
                for v in all_votes
            ],
            "result": winner,
        }
        self.window.append(voter_matrix)
        if len(self.window) > 5:
            self.window.pop(0)

        # 9. RL update
        metrics = self.model.update(winner)
        print(f"  Metrics: acc={metrics.get('accuracy')} loss={metrics.get('loss')}")

        # 10. Write to Firestore
        self._write_result(round_num, red, green, winner, prediction, metrics)
        self._write_metrics(round_num, metrics)
        self.model.save_rl("rl_weights.pkl")

        # 11. Local history
        self.round_history.append({
            "round": round_num, "green": green, "red": red, "winner": winner,
        })

        # 12. Advance round after remaining time
        await asyncio.sleep(ROUND_DURATION - VOTE_WINDOW)
        self._advance_round(round_num)

    # ── Firestore helpers ─────────────────────────────────────────────────
    def _read_human_votes(self, round_num: int) -> list[dict]:
        # Read ALL votes then filter in Python to avoid Firestore index issues
        ref  = self.db.collection("rounds").document(str(round_num)).collection("votes")
        snap = ref.get()
        return [d.to_dict() for d in snap if not d.to_dict().get("isAgent", False)]

    def _write_vote(self, round_num: int, user_id: str, data: dict):
        self.db.collection("rounds").document(str(round_num)) \
               .collection("votes").document(user_id).set(data)

    def _write_prediction(self, round_num: int, prediction: str):
        self.db.collection("roundResults").document(str(round_num)).set(
            {"prediction": prediction, "status": "pending"}, merge=True,
        )

    def _write_result(self, round_num, red, green, winner, prediction, metrics):
        self.db.collection("roundResults").document(str(round_num)).set({
            "round":      round_num,
            "redVotes":   red,
            "greenVotes": green,
            "winner":     winner,
            "prediction": prediction,
            "correct":    metrics.get("correct", False),
            "reward":     metrics.get("reward", 0),
            "accuracy":   metrics.get("accuracy", 0),
            "loss":       metrics.get("loss", 1),
            "timestamp":  int(time.time() * 1000),
            "status":     "done",
        })

    def _write_metrics(self, round_num: int, metrics: dict):
        self.db.collection("metrics").document(str(round_num)).set({
            "round":    round_num,
            "accuracy": metrics.get("accuracy", 0),
            "loss":     metrics.get("loss", 1),
            "reward":   metrics.get("reward", 0),
            "correct":  metrics.get("correct", False),
            "ts":       int(time.time() * 1000),
        })

    def _advance_round(self, current: int):
        ref  = self.db.collection("gameState").document("currentRound")
        snap = ref.get()
        if snap.exists and snap.to_dict().get("round") == current:
            ref.set({"round": current + 1, "startedAt": int(time.time() * 1000)})

    async def run(self, start_round: int = 1, total_rounds: int = 10_000):
        await self.bootstrap()
        for rnum in range(start_round, start_round + total_rounds):
            await self.run_round(rnum)

if __name__ == "__main__":
    manager = RoundManager()
    asyncio.run(manager.run())