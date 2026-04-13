"""
agent_voter.py
Standalone AI agent voter that syncs to Firestore round timing.

Timeline per round:
  0s  → 20s : humans vote  (agents wait)
  20s → 25s : agents vote  ← THIS SCRIPT FIRES HERE
  25s → 30s : HMNN predicts + results shown

The script watches gameState/currentRound and fires votes
during the 20-25s window of each round.
"""

import asyncio
import json
import random
import time
import os
import sys
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

try:
    from openai import AsyncOpenAI
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False

load_dotenv()

# ─── CONFIG ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY          = os.getenv("OPENAI_API_KEY")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

ROUND_DURATION  = 30   # must match useRoundTimer.js
HUMAN_CUTOFF    = 10   # humans stop at 10s remaining
AGENT_CUTOFF    = 5    # agents stop at 5s remaining
# Agent window: fires when timeRemaining is between 10 and 5 (i.e. at t=20s into round)

TOTAL_VOTES = 12

# ─── AGENTS ──────────────────────────────────────────────────────────────────
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

EMOTION_OPTIONS   = ["very_low", "low", "neutral", "strong", "very_strong"]
INFLUENCE_OPTIONS = ["no", "neutral", "yes"]

# ─── FIREBASE INIT ────────────────────────────────────────────────────────────
def init_firebase():
    if not firebase_admin._apps:
        if not FIREBASE_CREDENTIALS_PATH:
            raise ValueError("Missing FIREBASE_CREDENTIALS_PATH in .env")
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ─── OPENAI DECISION ──────────────────────────────────────────────────────────
async def get_agent_decision_openai(agent: dict, history: list) -> dict:
    if not _HAS_OPENAI or not OPENAI_API_KEY:
        return get_agent_decision_fallback(agent, history)

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
        return get_agent_decision_fallback(agent, history)

def get_agent_decision_fallback(agent: dict, history: list) -> dict:
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

# ─── FIRESTORE WRITE ──────────────────────────────────────────────────────────
def write_vote(db_client, round_num: int, agent: dict, decision: dict):
    db_client.collection("rounds").document(str(round_num)) \
             .collection("votes").document(agent["id"]) \
             .set({
                 "userId":           agent["id"],
                 "agentName":        agent["name"],
                 "color":            decision["color"],
                 "emotionFeel":      decision["emotionFeel"],
                 "influenceHistory": decision["influenceHistory"],
                 "timestamp":        int(time.time() * 1000),
                 "isAgent":          True,
             })

def get_human_vote_count(db_client, round_num: int) -> int:
    """Count how many humans have already voted this round."""
    ref  = db_client.collection("rounds").document(str(round_num)).collection("votes")
    snap = ref.get()
    return sum(1 for d in snap if not d.to_dict().get("isAgent", False))

def load_round_history(db_client, current_round: int) -> list:
    """Load last 5 round results for agent context."""
    history = []
    for rnum in range(max(1, current_round - 5), current_round):
        try:
            snap = db_client.collection("roundResults").document(str(rnum)).get()
            if snap.exists:
                d = snap.to_dict()
                if d.get("winner"):
                    history.append({
                        "round":  rnum,
                        "winner": d["winner"],
                        "red":    d.get("redVotes", 0),
                        "green":  d.get("greenVotes", 0),
                    })
        except Exception:
            pass
    return history

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────
async def main():
    db_client = init_firebase()
    print(f"[AgentVoter] Started at {datetime.now().strftime('%H:%M:%S')}")
    print(f"[AgentVoter] Will vote in the {HUMAN_CUTOFF}s–{AGENT_CUTOFF}s window of each round")

    processed_rounds = set()

    while True:
        try:
            # Read current round state
            snap = db_client.collection("gameState").document("currentRound").get()
            if not snap.exists:
                await asyncio.sleep(1)
                continue

            state      = snap.to_dict()
            round_num  = state.get("round", 1)
            started_at = state.get("startedAt", int(time.time() * 1000))

            # Calculate time position in this round
            elapsed_ms  = time.time() * 1000 - started_at
            elapsed_s   = elapsed_ms / 1000
            remaining_s = ROUND_DURATION - elapsed_s

            # ── Agent window: fire when 5s < remaining <= 10s ─────────────
            in_agent_window = AGENT_CUTOFF < remaining_s <= HUMAN_CUTOFF

            if in_agent_window and round_num not in processed_rounds:
                print(f"\n[AgentVoter] Round {round_num} — Agent window! ({remaining_s:.1f}s remaining)")
                processed_rounds.add(round_num)

                # Load history for context
                history = load_round_history(db_client, round_num)

                # How many agents do we need? (fill up to TOTAL_VOTES)
                human_count = get_human_vote_count(db_client, round_num)
                n_needed    = max(0, TOTAL_VOTES - human_count)
                agent_pool  = random.sample(AGENTS, n_needed) if n_needed else []

                print(f"  Humans voted: {human_count}, Agents needed: {n_needed}")

                if agent_pool:
                    # Fire all agent decisions concurrently
                    decisions = await asyncio.gather(*[
                        get_agent_decision_openai(a, history) for a in agent_pool
                    ])

                    red_count = green_count = 0
                    for agent, decision in zip(agent_pool, decisions):
                        write_vote(db_client, round_num, agent, decision)
                        if decision["color"] == "RED":
                            red_count += 1
                        else:
                            green_count += 1
                        print(f"  🤖 {agent['name']:8s} → {decision['color']}")

                    print(f"  Agents done: RED={red_count} GREEN={green_count}")
                else:
                    print(f"  All {TOTAL_VOTES} slots filled by humans, no agents needed.")

                # Keep processed_rounds from growing unbounded
                if len(processed_rounds) > 20:
                    oldest = min(processed_rounds)
                    processed_rounds.discard(oldest)

            # ── Sleep until next check ────────────────────────────────────
            # If we're before the agent window, sleep until we reach it
            if remaining_s > HUMAN_CUTOFF:
                sleep_for = remaining_s - HUMAN_CUTOFF - 0.5  # wake up 0.5s early
                sleep_for = max(0.5, min(sleep_for, 2.0))
            else:
                sleep_for = 0.3  # poll frequently during/after agent window

            await asyncio.sleep(sleep_for)

        except Exception as e:
            print(f"[AgentVoter] Error: {e}")
            await asyncio.sleep(2)

if __name__ == "__main__":
    if not FIREBASE_CREDENTIALS_PATH:
        print("ERROR: FIREBASE_CREDENTIALS_PATH not set in .env")
        sys.exit(1)
    asyncio.run(main())