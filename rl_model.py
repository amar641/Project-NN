"""
rl_model.py
HMNN wrapper with a lightweight contextual-bandit RL layer.

If HMNN.pkl exists and is loadable it is used directly.
The RL layer is a small logistic model that learns a correction
on top of HMNN's raw logits, so the base model is never retrained.

State  : last T=5 rounds → 15-dim vector
         [green_pct, red_pct, winner_int] × 5
Action : 0=RED, 1=GREEN  (argmax of corrected logits)
Reward : +1 correct, -1 wrong
"""

import os
import pickle
import numpy as np

# ─── Constants ───────────────────────────────────────────────────────────────
T           = 5          # window length (must match HMNN training)
STATE_DIM   = T * 3      # 3 features per round
HIDDEN      = 32         # hive dimension (must match saved model)
ALPHA       = 0.05       # RL learning rate
GAMMA_DECAY = 0.99       # reward discount (single-step bandit, kept light)

EMOTION_MAP = {
    "very_low": 0.00, "low": 0.25, "neutral": 0.50,
    "strong": 0.75, "very_strong": 1.00,
}
INFLUENCE_MAP = {"no": 0.10, "neutral": 0.50, "yes": 0.90}


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()


def _relu(x):
    return np.maximum(0, x)


def _sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -30, 30)))


def _softplus(x):
    return np.log1p(np.exp(np.clip(x, -30, 30)))


# ─── HMNN forward (pure numpy, mirrors the paper exactly) ────────────────────
class HMNNForward:
    """
    Runs a forward pass using the weight arrays loaded from HMNN.pkl.
    Expected pickle keys (match your training code):
        Wc, bc, Wo, bo, raw_gamma, raw_rho
    If keys differ, we fall back to random weights so the RL layer still runs.
    """

    def __init__(self, weights: dict):
        if weights:
            print(f"[HMNN] Keys in pkl: {list(weights.keys())}")

        def _get(d, *candidates):
            for k in candidates:
                if k in d:
                    return d[k]
            return None

        Wc        = _get(weights, "Wc", "W_c", "wc")
        bc        = _get(weights, "bc", "b_c", "bias_c")
        Wo        = _get(weights, "Wo", "W_o", "wo")
        bo        = _get(weights, "bo", "b_o", "bias_o")
        raw_gamma = _get(weights, "raw_gamma", "gamma", "raw_gamma_")
        raw_rho   = _get(weights, "raw_rho",   "rho",   "raw_rho_")

        if Wc is not None and Wo is not None:
            self.Wc        = np.array(Wc)
            self.bc        = np.array(bc) if bc is not None else np.zeros(np.array(Wc).shape[1])
            self.Wo        = np.array(Wo)
            self.bo        = np.array(bo) if bo is not None else np.zeros(np.array(Wo).shape[1])
            self.raw_gamma = float(raw_gamma) if raw_gamma is not None else 0.0
            self.raw_rho   = float(raw_rho)   if raw_rho   is not None else 0.5
            self.H         = self.Wc.shape[1]
            self._loaded   = True
            print(f"[HMNN] Weights loaded successfully. H={self.H}")
        else:
            print("[HMNN] Weight keys not found – using random init.")
            print(f"[HMNN] Available keys: {list(weights.keys()) if weights else 'none'}")
            self.H         = HIDDEN
            self.Wc        = np.random.randn(2, HIDDEN) * 0.1
            self.bc        = np.zeros(HIDDEN)
            self.Wo        = np.random.randn(HIDDEN, 2) * 0.1
            self.bo        = np.zeros(2)
            self.raw_gamma = 0.0
            self.raw_rho   = 0.5
            self._loaded   = False

    def forward(self, window: list[dict]) -> np.ndarray:
        """
        window : list of T dicts, each with keys:
                 votes  → list of {decision, emotion_level, influence}
                 result → 'RED'|'GREEN'
        Returns: raw logits shape (2,)
        """
        gamma = _softplus(self.raw_gamma)
        rho   = _sigmoid(self.raw_rho)
        N     = 12
        eps   = 1e-9

        h  = np.zeros(self.H)
        mu = None  # emotional momentum

        for t, rd in enumerate(window):
            votes = rd["votes"]          # list of N voter dicts
            d = np.array([v["decision"]          for v in votes], dtype=float)
            e = np.array([v["emotion_level"]     for v in votes], dtype=float)
            s = np.array([v["influence"]         for v in votes], dtype=float)

            # ── Influence Diffusion ──────────────────────────────────────────
            w  = _softmax(s)             # (N,)
            De = float(w @ e)            # weighted mean emotion
            Dd = float(w @ d)            # weighted mean decision
            D  = np.array([Dd, De])      # (2,)

            # ── Emotional Momentum ───────────────────────────────────────────
            e_bar = float(e.mean())
            if mu is None:
                mu = e_bar
            else:
                mu = rho * mu + (1 - rho) * e_bar

            # ── Consensus Pressure ───────────────────────────────────────────
            g = float(d.sum())
            r = N - g
            phi = (abs(r - g) / N + eps) ** gamma

            # ── Vote Entropy Dampener ────────────────────────────────────────
            pg = g / N + eps
            pr = r / N + eps
            eta = -pr * np.log2(pr) - pg * np.log2(pg)
            eta = float(np.clip(eta, 0, 1))

            # ── Scalar update ────────────────────────────────────────────────
            scale = phi * mu * (1 - eta)

            # ── Candidate state ──────────────────────────────────────────────
            z = D @ self.Wc + self.bc    # (H,)
            c = _relu(z)

            # ── Hive update ──────────────────────────────────────────────────
            h = h + scale * (c - h)

        logits = h @ self.Wo + self.bo   # (2,)
        return logits


# ─── RL correction layer ──────────────────────────────────────────────────────
class RLCorrection:
    """
    Tiny logistic correction trained online via policy-gradient (REINFORCE).
    Input  : STATE_DIM-dim state vector
    Output : 2-dim correction added to HMNN logits
    """

    def __init__(self):
        self.W = np.zeros((STATE_DIM, 2))   # correction weights
        self.b = np.zeros(2)
        self.lr = ALPHA

    def forward(self, state: np.ndarray) -> np.ndarray:
        return state @ self.W + self.b      # (2,)

    def update(self, state: np.ndarray, action: int, reward: float):
        """REINFORCE-style gradient ascent on log-prob of taken action."""
        correction = self.forward(state)    # (2,)
        probs      = _softmax(correction)   # (2,)

        # gradient: ∇log π(a|s) = one_hot(a) - probs
        one_hot         = np.zeros(2)
        one_hot[action] = 1.0
        delta           = reward * (one_hot - probs)  # (2,)

        self.W += self.lr * np.outer(state, delta)
        self.b += self.lr * delta

    def to_dict(self) -> dict:
        return {"W": self.W.tolist(), "b": self.b.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> "RLCorrection":
        obj   = cls()
        obj.W = np.array(d["W"])
        obj.b = np.array(d["b"])
        return obj


# ─── Public API ───────────────────────────────────────────────────────────────
class RLModel:
    """
    The main object used by round_manager.py.
    """

    def __init__(self, pkl_path: str = "HMNN.pkl"):
        # Load base model
        if os.path.exists(pkl_path):
            with open(pkl_path, "rb") as f:
                weights = pickle.load(f)
            print(f"[RLModel] Loaded HMNN weights from {pkl_path}")
        else:
            print(f"[RLModel] {pkl_path} not found – using random weights")
            weights = {}

        self.hmnn       = HMNNForward(weights)
        self.rl         = RLCorrection()
        self.history    = []          # list of round dicts for metrics
        self.last_state = None
        self.last_action = None

    # ── Build state vector from last T round summaries ────────────────────
    @staticmethod
    def build_state(round_summaries: list[dict]) -> np.ndarray:
        """
        round_summaries: list of up to T dicts
          { "green": int, "red": int, "winner": "RED"|"GREEN" }
        Returns a flat (T*3,) numpy array, zero-padded for early rounds.
        """
        state = np.zeros(STATE_DIM)
        for i, rs in enumerate(round_summaries[-T:]):
            offset        = i * 3
            total         = rs["green"] + rs["red"] + 1e-9
            state[offset]     = rs["green"] / total
            state[offset + 1] = rs["red"]   / total
            state[offset + 2] = 1.0 if rs["winner"] == "GREEN" else 0.0
        return state

    # ── Predict next round winner ─────────────────────────────────────────
    def predict(self, window: list[dict], round_summaries: list[dict]) -> str:
        """
        window         : last T rounds of voter matrices (for HMNN forward)
        round_summaries: last T round aggregate dicts   (for RL state)
        Returns "RED" or "GREEN"
        """
        # HMNN logits
        if len(window) >= T:
            hmnn_logits = self.hmnn.forward(window[-T:])
        else:
            hmnn_logits = np.zeros(2)

        # RL correction
        state          = self.build_state(round_summaries)
        rl_correction  = self.rl.forward(state)
        combined       = hmnn_logits + rl_correction
        probs          = _softmax(combined)
        action         = int(np.argmax(probs))       # 0=RED, 1=GREEN

        self.last_state  = state
        self.last_action = action

        return "GREEN" if action == 1 else "RED"

    # ── Update after round resolves ───────────────────────────────────────
    def update(self, actual_winner: str) -> dict:
        """
        Call after a round finishes to apply the RL update.
        Returns a metrics dict.
        """
        if self.last_state is None:
            return {}

        actual_action = 1 if actual_winner == "GREEN" else 0
        reward        = 1.0 if self.last_action == actual_action else -1.0

        self.rl.update(self.last_state, self.last_action, reward)

        predicted = "GREEN" if self.last_action == 1 else "RED"
        correct   = predicted == actual_winner

        self.history.append({
            "predicted": predicted,
            "actual":    actual_winner,
            "reward":    reward,
            "correct":   correct,
        })

        # Running accuracy & loss
        n_total   = len(self.history)
        n_correct = sum(1 for h in self.history if h["correct"])
        accuracy  = n_correct / n_total
        loss      = 1.0 - accuracy          # simple 0/1 loss

        self.last_state  = None
        self.last_action = None

        return {
            "predicted":  predicted,
            "actual":     actual_winner,
            "reward":     reward,
            "correct":    correct,
            "accuracy":   round(accuracy, 4),
            "loss":       round(loss, 4),
            "n_rounds":   n_total,
        }

    # ── Serialize RL weights (for cold restart persistence) ──────────────
    def save_rl(self, path: str = "rl_weights.pkl"):
        with open(path, "wb") as f:
            pickle.dump(self.rl.to_dict(), f)

    def load_rl(self, path: str = "rl_weights.pkl"):
        if os.path.exists(path):
            with open(path, "rb") as f:
                d = pickle.load(f)
            self.rl = RLCorrection.from_dict(d)
            print(f"[RLModel] Loaded RL weights from {path}")


# ─── Encoding helpers (shared with round_manager) ────────────────────────────
def encode_vote(color: str, emotion: str, influence: str) -> dict:
    """Convert raw strings to normalised floats for the HMNN forward pass."""
    return {
        "decision":      1.0 if color == "GREEN" else 0.0,
        "emotion_level": EMOTION_MAP.get(emotion, 0.5),
        "influence":     INFLUENCE_MAP.get(influence, 0.5),
    }