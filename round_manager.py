"""
round_manager.py
Orchestrates each voting round with a 3-phase timing model:

  Phase 1 — Human voting   (0s  → 20s): humans cast votes via the web UI
  Phase 2 — Agent voting   (20s → 25s): AI agents cast their votes
  Phase 3 — Prediction     (25s → 30s): HMNN computes & publishes prediction,
                                         frontend displays it in the last 5s
  End of round             (30s)       : tally, RL update, metrics, advance round
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

# ─── Timing Config ────────────────────────────────────────────────────────────
ROUND_DURATION   = 30   # total round length (seconds)
HUMAN_CUTOFF     = 10   # humans stop voting when 10s remain  (at t=20s)
AGENT_WINDOW     = 5    # agents have 5s to vote              (t=20s → t=25s)
PREDICT_WINDOW   = 5    # prediction shown in last 5s         (t=25s → t=30s)

HUMAN_VOTE_TIME  = ROUND_DURATION - HUMAN_CUTOFF   # 20s  — wait for humans
AGENT_END_TIME   = ROUND_DURATION - (HUMAN_CUTOFF - AGENT_WINDOW)  # 25s
# After AGENT_END_TIME we compute, write prediction, then sleep remaining

TOTAL_VOTES      = 12
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
FIREBASE_CRED    = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccount.json")

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

# ─── Agent decision via OpenAI ────────────────────────────────────────────────
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
        self.round_history: list[dict] = []   # aggregate round results
        self.window:        list[dict] = []   # voter-matrix window for HMNN

    # ── Bootstrap: load last 5 completed rounds from Firestore ───────────
    async def bootstrap(self):
        snap = self.db.collection("gameState").document("currentRound").get()
        if not snap.exists:
            return
        current = snap.to_dict().get("round", 1)
        print(f"[Bootstrap] Current round: {current}")
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
                    print(f"  Loaded round {rnum}: {d.get('winner')}")
            except Exception as e:
                print(f"  Bootstrap error round {rnum}: {e}")

    # ── Main round orchestration ──────────────────────────────────────────
    async def run_round(self, round_num: int):
        round_start = time.time()
        print(f"\n{'='*50}")
        print(f"[Round {round_num}] START — {time.strftime('%H:%M:%S')}")
        print(f"{'='*50}")

        # ── Phase 1: Wait for human votes (0s → 20s) ─────────────────────
        print(f"[Round {round_num}] Phase 1: Human voting open (0s → {HUMAN_VOTE_TIME}s)")
        await asyncio.sleep(HUMAN_VOTE_TIME)

        # ── Phase 2: Agent voting (20s → 25s) ────────────────────────────
        print(f"[Round {round_num}] Phase 2: Agent voting ({HUMAN_VOTE_TIME}s → {AGENT_END_TIME}s)")

        # Read current human votes first
        human_votes = self._read_human_votes(round_num)
        print(f"  Human votes collected: {len(human_votes)}")

        # Determine how many agents needed
        n_needed   = max(0, TOTAL_VOTES - len(human_votes))
        agent_pool = random.sample(AGENTS, n_needed) if n_needed else []
        print(f"  Agents needed: {n_needed}")

        # Fire all agent decisions concurrently (they have 5s)
        agent_task = asyncio.create_task(
            self._get_all_agent_decisions(agent_pool, round_num)
        )

        # Wait for agent window to finish
        elapsed   = time.time() - round_start
        remaining = max(0, AGENT_END_TIME - elapsed)
        await asyncio.sleep(remaining)

        # Collect agent results (should be done by now, but await with timeout)
        try:
            agent_votes = await asyncio.wait_for(agent_task, timeout=3.0)
        except asyncio.TimeoutError:
            agent_votes = []
            print("  WARNING: Agent voting timed out, using fallback")
            agent_votes = self._fallback_agent_votes(agent_pool, round_num)

        print(f"  Agent votes written: {len(agent_votes)}")

        # ── Phase 3: HMNN Prediction (25s → 30s) ─────────────────────────
        print(f"[Round {round_num}] Phase 3: Computing HMNN prediction ({AGENT_END_TIME}s → {ROUND_DURATION}s)")

        # Re-read all votes now that agents have voted
        human_votes_final = self._read_human_votes(round_num)
        all_votes_so_far  = human_votes_final + agent_votes

        # Build current round's voter matrix for HMNN (use what we have)
        if len(all_votes_so_far) > 0:
            current_matrix = {
                "votes": [
                    encode_vote(v["color"], v["emotionFeel"], v["influenceHistory"])
                    for v in all_votes_so_far
                ],
                "result": None,  # unknown yet
            }
            window_for_predict = self.window + [current_matrix]
        else:
            window_for_predict = self.window

        # Compute prediction using last 5 rounds of history + current partial data
        prediction = self.model.predict(window_for_predict, self.round_history)
        print(f"  HMNN Prediction: {prediction}")

        # Write prediction to Firestore — frontend will display it
        self._write_prediction(round_num, prediction)

        # Wait out the remaining prediction window
        elapsed   = time.time() - round_start
        remaining = max(0, ROUND_DURATION - elapsed)
        if remaining > 0:
            await asyncio.sleep(remaining)

        # ── Tally ─────────────────────────────────────────────────────────
        all_votes = self._read_all_votes(round_num)
        red   = sum(1 for v in all_votes if v["color"] == "RED")
        green = sum(1 for v in all_votes if v["color"] == "GREEN")
        winner = "RED" if red > green else "GREEN" if green > red else "TIE"
        print(f"  TALLY: RED={red} GREEN={green} → WINNER={winner}")

        # ── Build voter matrix for HMNN update ───────────────────────────
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

        # ── RL update (now that we know the actual winner) ────────────────
        metrics = self.model.update(winner)
        print(f"  Metrics: acc={metrics.get('accuracy')} loss={metrics.get('loss')} correct={metrics.get('correct')}")

        # ── Write results to Firestore ────────────────────────────────────
        self._write_result(round_num, red, green, winner, prediction, metrics)
        self._write_metrics(round_num, metrics)
        self.model.save_rl("rl_weights.pkl")

        # ── Update local history ──────────────────────────────────────────
        self.round_history.append({
            "round":  round_num,
            "green":  green,
            "red":    red,
            "winner": winner,
        })
        # Keep only last 5
        if len(self.round_history) > 5:
            self.round_history = self.round_history[-5:]

        # ── Advance round ─────────────────────────────────────────────────
        self._advance_round(round_num)
        print(f"[Round {round_num}] COMPLETE → advanced to round {round_num + 1}")

    # ── Get all agent decisions and write them concurrently ───────────────
    async def _get_all_agent_decisions(self, agent_pool: list, round_num: int) -> list:
        if not agent_pool:
            return []

        decisions = await asyncio.gather(*[
            get_agent_decision(a, self.round_history) for a in agent_pool
        ])

        agent_votes = []
        for agent, decision in zip(agent_pool, decisions):
            vote = {
                "userId":           agent["id"],
                "agentName":        agent["name"],
                "color":            decision["color"],
                "emotionFeel":      decision["emotionFeel"],
                "influenceHistory": decision["influenceHistory"],
                "isAgent":          True,
                "votedAt":          int(time.time() * 1000),
            }
            self._write_vote(round_num, agent["id"], vote)
            agent_votes.append(vote)

        return agent_votes

    def _fallback_agent_votes(self, agent_pool: list, round_num: int) -> list:
        votes = []
        for agent in agent_pool:
            d = _agent_fallback(agent, self.round_history)
            vote = {
                "userId":           agent["id"],
                "agentName":        agent["name"],
                "color":            d["color"],
                "emotionFeel":      d["emotionFeel"],
                "influenceHistory": d["influenceHistory"],
                "isAgent":          True,
                "votedAt":          int(time.time() * 1000),
            }
            self._write_vote(round_num, agent["id"], vote)
            votes.append(vote)
        return votes

    # ── Firestore helpers ─────────────────────────────────────────────────
    def _read_human_votes(self, round_num: int) -> list[dict]:
        ref  = self.db.collection("rounds").document(str(round_num)).collection("votes")
        snap = ref.get()
        return [d.to_dict() for d in snap if not d.to_dict().get("isAgent", False)]

    def _read_all_votes(self, round_num: int) -> list[dict]:
        ref  = self.db.collection("rounds").document(str(round_num)).collection("votes")
        snap = ref.get()
        return [d.to_dict() for d in snap]

    def _write_vote(self, round_num: int, user_id: str, data: dict):
        self.db.collection("rounds").document(str(round_num)) \
               .collection("votes").document(user_id).set(data)

    def _write_prediction(self, round_num: int, prediction: str):
        """Write prediction so frontend can show it in last 5 seconds."""
        self.db.collection("roundResults").document(str(round_num)).set(
            {
                "prediction": prediction,
                "status":     "predicting",
                "predictedAt": int(time.time() * 1000),
            },
            merge=True,
        )

    def _write_result(self, round_num, red, green, winner, prediction, metrics):
        self.db.collection("roundResults").document(str(round_num)).set({
            "round":       round_num,
            "redVotes":    red,
            "greenVotes":  green,
            "winner":      winner,
            "prediction":  prediction,
            "correct":     metrics.get("correct", False),
            "reward":      metrics.get("reward", 0),
            "accuracy":    metrics.get("accuracy", 0),
            "loss":        metrics.get("loss", 1),
            "timestamp":   int(time.time() * 1000),
            "status":      "done",
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
        snap = self.db.collection("gameState").document("currentRound").get()
        if snap.exists:
            start_round = snap.to_dict().get("round", 1)
        print(f"\n[RoundManager] Starting from round {start_round}")
        for rnum in range(start_round, start_round + total_rounds):
            await self.run_round(rnum)


if __name__ == "__main__":
    manager = RoundManager()
    asyncio.run(manager.run())