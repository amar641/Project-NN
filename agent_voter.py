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
from openai import AsyncOpenAI

load_dotenv()

# ─── CONFIG ─────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

TOTAL_ROUNDS = 1000
ROUND_DURATION = 2
NUM_AGENTS = 12
VOTE_WINDOW = 1.6

# ─── INIT FIREBASE (SECURE) ─────────────────────────
def init_firebase():
    if not firebase_admin._apps:
        if not FIREBASE_CREDENTIALS_PATH:
            raise ValueError("Missing FIREBASE_CREDENTIALS_PATH in .env")

        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ─── INIT OPENAI ────────────────────────────────────
if not OPENAI_API_KEY:
    print("ERROR: OPENAI_API_KEY not set in .env")
    sys.exit(1)

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ─── AGENTS (UNCHANGED) ─────────────────────────────
AGENTS = [
    {"id": "agent_001", "name": "Aria", "personality": "Optimistic and trend-following.", "emotion_bias": "very_strong", "history_bias": "yes", "risk_tolerance": "medium", "contrarian": False},
    {"id": "agent_002", "name": "Brutus", "personality": "Stubborn contrarian.", "emotion_bias": "low", "history_bias": "no", "risk_tolerance": "high", "contrarian": True},
    {"id": "agent_003", "name": "Cleo", "personality": "Analytical and cautious.", "emotion_bias": "neutral", "history_bias": "yes", "risk_tolerance": "low", "contrarian": False},
    {"id": "agent_004", "name": "Drake", "personality": "Momentum trader.", "emotion_bias": "strong", "history_bias": "yes", "risk_tolerance": "high", "contrarian": False},
    {"id": "agent_005", "name": "Elsa", "personality": "Random voter.", "emotion_bias": "very_low", "history_bias": "no", "risk_tolerance": "medium", "contrarian": False},
    {"id": "agent_006", "name": "Felix", "personality": "Mean-reversion believer.", "emotion_bias": "neutral", "history_bias": "yes", "risk_tolerance": "medium", "contrarian": True},
    {"id": "agent_007", "name": "Gina", "personality": "Emotional and impulsive.", "emotion_bias": "very_strong", "history_bias": "neutral", "risk_tolerance": "high", "contrarian": False},
    {"id": "agent_008", "name": "Hiro", "personality": "Disciplined system voter.", "emotion_bias": "low", "history_bias": "yes", "risk_tolerance": "low", "contrarian": False},
    {"id": "agent_009", "name": "Iris", "personality": "Social mimic.", "emotion_bias": "strong", "history_bias": "yes", "risk_tolerance": "medium", "contrarian": False},
    {"id": "agent_010", "name": "Jules", "personality": "Pessimist.", "emotion_bias": "strong", "history_bias": "neutral", "risk_tolerance": "low", "contrarian": False},
    {"id": "agent_011", "name": "Kai", "personality": "Balanced thinker.", "emotion_bias": "neutral", "history_bias": "neutral", "risk_tolerance": "medium", "contrarian": False},
    {"id": "agent_012", "name": "Luna", "personality": "Superstitious.", "emotion_bias": "very_strong", "history_bias": "yes", "risk_tolerance": "high", "contrarian": False},
]

# ─── OPENAI DECISION ────────────────────────────────
async def get_agent_decision(agent, round_num, history):
    prompt = f"""
You are {agent['name']}.
Personality: {agent['personality']}

Choose RED or GREEN.
Respond JSON:
{{"color":"RED","emotionFeel":"neutral","influenceHistory":"yes"}}
"""

    try:
        res = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0.8
        )
        raw = res.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "")
        return json.loads(raw)

    except Exception:
        return {
            "color": random.choice(["RED", "GREEN"]),
            "emotionFeel": agent["emotion_bias"],
            "influenceHistory": agent["history_bias"],
        }

# ─── FIRESTORE WRITE ────────────────────────────────
def write_vote(db, round_num, agent, decision):
    db.collection("rounds").document(str(round_num)) \
      .collection("votes").document(agent["id"]) \
      .set({
          "userId": agent["id"],
          "agentName": agent["name"],
          "color": decision["color"],
          "emotionFeel": decision["emotionFeel"],
          "influenceHistory": decision["influenceHistory"],
          "timestamp": int(time.time()*1000),
          "isAgent": True
      })

# ─── MAIN LOOP ──────────────────────────────────────
async def main():
    db = init_firebase()
    history = []

    for round_num in range(1, TOTAL_ROUNDS + 1):
        print(f"\nROUND {round_num}")

        tasks = [get_agent_decision(a, round_num, history) for a in AGENTS]
        decisions = await asyncio.gather(*tasks)

        red, green = 0, 0

        for agent, decision in zip(AGENTS, decisions):
            write_vote(db, round_num, agent, decision)
            if decision["color"] == "RED":
                red += 1
            else:
                green += 1

        winner = "RED" if red > green else "GREEN"
        history.append({"winner": winner})

        print(f"RED: {red} | GREEN: {green} | WINNER: {winner}")

        await asyncio.sleep(ROUND_DURATION)

if __name__ == "__main__":
    asyncio.run(main())