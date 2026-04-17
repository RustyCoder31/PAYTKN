"""Market sentiment model.

Sentiment is a continuous value in [0, 1]:
  0.0 = extreme fear / crash
  0.5 = neutral
  1.0 = extreme greed / euphoria

It acts as the ecosystem's "weather" — driving signup rates, user activity,
speculator behaviour, and staking/unstaking pressure.

Update rule (each day):
  1. Compute signal from price momentum, volatility, treasury health
  2. Apply tanh squashing so extreme events move sentiment hard but it can't escape [0,1]
  3. Drift back toward neutral (mean reversion) at rate `drift`
  4. Add small Gaussian noise
"""

from __future__ import annotations
import numpy as np


class MarketSentiment:
    """First-class dynamic variable — updated every day by the simulator."""

    def __init__(
        self,
        initial: float = 0.55,
        drift: float = 0.02,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.value: float = float(np.clip(initial, 0.0, 1.0))
        self.drift = drift   # mean-reversion strength toward 0.5
        self.rng = rng if rng is not None else np.random.default_rng()

        # Rolling price history for momentum (last 7 days)
        self._price_history: list[float] = []

    def update(
        self,
        price: float,
        price_yesterday: float,
        volatility: float,       # price std over last N days (normalised)
        treasury_health: float,  # treasury_stable / initial_treasury_stable (0..∞, capped at 2)
        active_users: int,
        prev_users: int,
    ) -> float:
        """Compute and store new sentiment value. Returns updated value."""

        # --- Price momentum signal [-1, 1] ---
        price_return = (price - price_yesterday) / (price_yesterday + 1e-8)
        momentum_signal = float(np.tanh(price_return * 10.0))

        # --- Volatility penalty (high vol → fear) ---
        vol_signal = -float(np.tanh(volatility * 5.0))

        # --- Treasury health signal ---
        t_capped = min(treasury_health, 2.0)
        treasury_signal = float(np.tanh((t_capped - 1.0) * 2.0))

        # --- User growth signal ---
        if prev_users > 0:
            growth = (active_users - prev_users) / prev_users
            growth_signal = float(np.tanh(growth * 20.0))
        else:
            growth_signal = 0.0

        # --- Weighted composite raw signal ---
        raw = (
            0.40 * momentum_signal
            + 0.20 * vol_signal
            + 0.25 * treasury_signal
            + 0.15 * growth_signal
        )

        # --- Shift current sentiment toward signal ---
        # raw in [-1,1] → translated to [-0.5, 0.5] nudge
        nudge = raw * 0.05
        new_value = self.value + nudge

        # --- Mean reversion toward 0.5 ---
        new_value += self.drift * (0.5 - new_value)

        # --- Small noise ---
        noise = float(self.rng.normal(0.0, 0.01))
        new_value += noise

        self.value = float(np.clip(new_value, 0.0, 1.0))
        return self.value

    def is_bull(self) -> bool:
        return self.value >= 0.65

    def is_bear(self) -> bool:
        return self.value <= 0.35

    def label(self) -> str:
        if self.value >= 0.65:
            return "bull"
        if self.value <= 0.35:
            return "bear"
        return "neutral"
