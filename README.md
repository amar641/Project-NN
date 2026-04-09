# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is enabled on this template. See [this documentation](https://react.dev/learn/react-compiler) for more information.

Note: This will impact Vite dev & build performances.

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.


# Project NN — AI Agent Voter Simulation

## What this does
Runs **12 independent AI agents** that vote RED or GREEN on your Firebase voting site.
- Each agent has a unique personality, emotional style, and decision logic
- Agents use OpenAI GPT-4o-mini to reason about past rounds and decide
- Votes are written directly to your Firebase Firestore
- 1000 rounds × 12 agents = **12,000 total votes**
- Round duration is set to 2 seconds (vs 30s for humans)

## Setup

### 1. Install dependencies
```bash
pip install firebase-admin openai
```

### 2. Set your OpenAI API key
```bash
# Mac/Linux:
export OPENAI_API_KEY="sk-your-key-here"

# Windows CMD:
set OPENAI_API_KEY=sk-your-key-here

# Windows PowerShell:
$env:OPENAI_API_KEY="sk-your-key-here"
```

### 3. Run
```bash
python agent_voter.py
```

## The 12 Agents

| # | Name   | Personality                                      |
|---|--------|--------------------------------------------------|
| 1 | Aria   | Optimistic trend-follower, high emotion          |
| 2 | Brutus | Stubborn contrarian, bets against the crowd      |
| 3 | Cleo   | Analytical, cautious, data-driven                |
| 4 | Drake  | Momentum trader, rides streaks                   |
| 5 | Elsa   | Pure gut instinct, ignores history               |
| 6 | Felix  | Mean-reversion believer, statistical thinker     |
| 7 | Gina   | Emotional & impulsive, reactive to losses        |
| 8 | Hiro   | Disciplined systems voter, structured patterns   |
| 9 | Iris   | Social mimic, follows perceived crowd            |
|10 | Jules  | Pessimist, bias toward RED (danger signal)       |
|11 | Kai    | Balanced philosopher, weighs both sides          |
|12 | Luna   | Superstitious, sees patterns in noise            |

## Estimated Cost
- Model: `gpt-4o-mini` (cheapest capable model)
- Tokens per call: ~200 input + 30 output ≈ 230 tokens
- Calls: 1000 rounds × 12 agents = 12,000 calls
- Total tokens: ~2.76M tokens
- Estimated cost: **~$0.50–$1.00 USD** at gpt-4o-mini rates

## Output Example
```
══════════════════════════════════════════
  ROUND 0001 / 1000   [14:32:01]
══════════════════════════════════════════
  All agents decided in 1.24s
  🔴 Aria   → RED   | emotion=very_strong  | history=yes
  🟢 Brutus → GREEN | emotion=low          | history=no
  🟢 Cleo   → GREEN | emotion=neutral      | history=yes
  ...
  RESULT → 🔴 RED: 4  |  🟢 GREEN: 8  |  Winner: GREEN
```

## Notes
- The web UI (your React app) will show live vote counts as agents vote
- The `gameState/currentRound` doc is updated each round so the UI tracks it
- If an OpenAI call fails, the agent falls back to its persona-based defaults
- You can interrupt and restart — rounds are independent