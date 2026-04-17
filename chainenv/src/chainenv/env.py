"""PaytknEnv — Gymnasium environment wrapping the full ChainEnv simulation.

Observation space (15-dim, all normalised to [0, 1] or [-1, 1]):
  0  price_ratio         current_price / initial_price  (clipped at 3x)
  1  volatility          7-day price std / initial_price (clipped at 1)
  2  tx_volume_norm      daily_tx_volume / 1_000_000
  3  active_users_norm   active_users / 10_000
  4  sentiment           raw [0, 1]
  5  treasury_health     treasury_stable / initial_stable (clipped at 2)
  6  treasury_paytkn_norm treasury_paytkn / initial_treasury_paytkn (clipped at 2)
  7  staking_ratio       total_staked / total_supply (clipped at 1)
  8  supply_inflation    total_supply / initial_supply - 1 (clipped at 1)
  9  burn_rate_today     daily_burn / initial_supply (clipped at 0.01, normalised)
 10  reward_pool_norm    reward_pool / initial_supply (clipped at 0.5)
 11  day_norm            day / episode_days
 12  user_growth_rate    (active_users - prev_users) / max(1, prev_users) (clipped ±0.5)
 13  merchant_count_norm active_merchants / 1_000
 14  loyalty_avg         mean loyalty score of active users [0, 1]

Action space (5-dim continuous, all in [-1, 1]):
  0  mint_rate   → mapped to [0.0, 0.05]
  1  burn_pct    → mapped to [0.001, 0.03]
  2  staking_apy → mapped to [0.02, 0.25]
  3  treasury_ratio → mapped to [0.6, 0.9]
  4  reward_alloc  → mapped to [0.1, 0.4]

Reward = weighted sum (see RewardWeights) + penalties for volatility, inflation, churn.
"""

from __future__ import annotations
from typing import Any
import numpy as np
import gymnasium as gym
from gymnasium import spaces

from chainenv.config import SimConfig, map_action
from chainenv.economy import Economy
from chainenv.sentiment import MarketSentiment
from chainenv.population import PopulationManager
from chainenv.actions import ActionKind


OBS_DIM = 15
ACT_DIM = 5


class PaytknEnv(gym.Env):
    """ChainEnv Gymnasium environment — PAYTKN tokenomics simulator."""

    metadata = {"render_modes": []}

    def __init__(self, cfg: SimConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg or SimConfig()

        self.observation_space = spaces.Box(
            low=-1.0, high=2.0, shape=(OBS_DIM,), dtype=np.float32,
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(ACT_DIM,), dtype=np.float32,
        )

        # Set during reset
        self._economy: Economy | None = None
        self._sentiment: MarketSentiment | None = None
        self._pop: PopulationManager | None = None
        self._rng: np.random.Generator | None = None
        self._day: int = 0
        self._price_history: list[float] = []
        self._prev_active_users: int = 0
        self._prev_treasury_stable: float = 0.0
        self._prev_supply: float = 0.0
        self._episode_metrics: list[dict] = []

    # ─────────────────────────────────────────────────────────
    # Gymnasium API
    # ─────────────────────────────────────────────────────────

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict | None = None,
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)

        rng_seed = seed if seed is not None else self.cfg.rng_seed
        self._rng = np.random.default_rng(rng_seed)

        self._economy = Economy(self.cfg)
        self._sentiment = MarketSentiment(
            initial=self.cfg.initial_sentiment,
            drift=self.cfg.sentiment_drift,
            rng=np.random.default_rng(rng_seed + 1),
        )
        self._pop = PopulationManager(self.cfg, np.random.default_rng(rng_seed + 2))
        self._pop.seed_initial()

        self._day = 0
        self._price_history = [self.cfg.initial_price]
        self._prev_active_users = len(self._pop.active_users)
        self._prev_treasury_stable = self.cfg.initial_treasury_stable
        self._prev_supply = self.cfg.initial_supply
        self._episode_metrics = []

        return self._get_obs(), {}

    def step(
        self, action: np.ndarray
    ) -> tuple[np.ndarray, float, bool, bool, dict]:
        assert self._economy is not None, "Call reset() first."

        # 1. Apply agent levers
        b = self.cfg.bounds
        self._economy.apply_agent_levers(
            mint_rate=map_action(float(action[0]), *b.mint_rate),
            burn_pct=map_action(float(action[1]), *b.burn_pct),
            staking_apy=map_action(float(action[2]), *b.staking_apy),
            treasury_ratio=map_action(float(action[3]), *b.treasury_ratio),
            reward_alloc=map_action(float(action[4]), *b.reward_alloc),
        )

        # 2. Begin day
        self._economy.begin_day()
        self._day += 1

        # 3. Population update
        new_u, churned = self._pop.daily_update(self._sentiment.value)
        if self._day % 7 == 0:
            self._pop.weekly_reset()

        # 4. Entity actions → economy
        active_merchants = self._pop.active_merchants
        active_users = self._pop.active_users

        for user in active_users:
            actions = user.decide_day_actions(
                rng=self._rng,
                sentiment=self._sentiment.value,
                price=self._economy.price,
                staking_apy=self._economy.current_staking_apy,
                rules=self.cfg.rules,
                merchants=active_merchants,
            )
            self._process_user_actions(actions, user)

        for merchant in active_merchants:
            m_actions = merchant.decide_day_actions(
                rng=self._rng,
                sentiment=self._sentiment.value,
                price=self._economy.price,
                staking_apy=self._economy.current_staking_apy,
                rules=self.cfg.rules,
            )
            self._process_merchant_actions(m_actions, merchant)

        # 5. End day (mint + distribute rewards + rebalance)
        n_active_u = len(active_users)
        n_active_m = len(active_merchants)
        metrics = self._economy.end_day(n_active_u, n_active_m)

        # 6. Update sentiment
        price_yesterday = self._price_history[-1]
        volatility = self._compute_volatility()
        treasury_health = (
            self._economy.treasury_stable / max(1.0, self.cfg.initial_treasury_stable)
        )
        self._sentiment.update(
            price=self._economy.price,
            price_yesterday=price_yesterday,
            volatility=volatility,
            treasury_health=treasury_health,
            active_users=n_active_u,
            prev_users=self._prev_active_users,
        )

        # 7. Record history
        self._price_history.append(self._economy.price)

        # 8. Compute reward
        reward = self._compute_reward(
            metrics=metrics,
            churned=churned,
            n_active_u=n_active_u,
        )

        # 9. Log metrics
        self._episode_metrics.append({
            "day": self._day,
            "price": self._economy.price,
            "sentiment": self._sentiment.value,
            "active_users": n_active_u,
            "treasury_stable": self._economy.treasury_stable,
            "treasury_paytkn": self._economy.treasury_paytkn,
            "total_supply": self._economy.total_supply,
            "tx_volume": metrics.daily_tx_volume,
            "daily_fees": metrics.daily_fees_collected,
            "daily_rewards": metrics.daily_rewards_paid,
            "staked": self._economy.total_staked,
            "reward": reward,
        })

        # 10. Update prev-day values
        self._prev_active_users = n_active_u
        self._prev_treasury_stable = self._economy.treasury_stable
        self._prev_supply = self._economy.total_supply

        terminated = self._day >= self.cfg.episode_days
        truncated = False

        return self._get_obs(), reward, terminated, truncated, {"metrics": metrics}

    # ─────────────────────────────────────────────────────────
    # Action processing helpers
    # ─────────────────────────────────────────────────────────

    def _process_user_actions(self, actions, user) -> None:
        eco = self._economy
        for act in actions:
            if act.kind == ActionKind.PAYMENT and act.target_id:
                net = eco.process_payment(act.actor_id, act.target_id, act.amount)
                # Credit net to merchant wallet
                for m in self._pop.active_merchants:
                    if m.merchant_id == act.target_id:
                        m.receive_payment(net)
                        break
            elif act.kind == ActionKind.STAKE:
                eco.record_stake(act.amount)
            elif act.kind == ActionKind.UNSTAKE:
                eco.record_unstake(act.amount)
            elif act.kind == ActionKind.BUY:
                received = eco.execute_buy(act.actor_id, act.amount)
                user.wallet += received
            elif act.kind == ActionKind.SELL:
                received = eco.execute_sell(act.actor_id, act.amount)
                # Stablecoins received — user could re-enter; simplified: wallet net zero
            elif act.kind == ActionKind.INVITE:
                pass  # Tracked at population level; reward via loyalty multiplier
            elif act.kind == ActionKind.CANCEL:
                pass  # Already handled in decide_day_actions

    def _process_merchant_actions(self, actions, merchant) -> None:
        eco = self._economy
        for act in actions:
            if act.kind == ActionKind.STAKE:
                eco.record_stake(act.amount)
            elif act.kind == ActionKind.LOAN_TAKE:
                approved = eco.process_loan_take(
                    merchant_id=act.actor_id,
                    amount=act.amount,
                    merchant_staked=merchant.staked,
                    price=eco.price,
                )
                merchant.loan_outstanding = approved
            elif act.kind == ActionKind.LOAN_REPAY:
                eco.process_loan_repay(act.actor_id, act.amount)

    # ─────────────────────────────────────────────────────────
    # Observation
    # ─────────────────────────────────────────────────────────

    def _get_obs(self) -> np.ndarray:
        eco = self._economy
        cfg = self.cfg

        if eco is None:
            return np.zeros(OBS_DIM, dtype=np.float32)

        n_users = len(self._pop.active_users) if self._pop else cfg.initial_users
        n_merchants = len(self._pop.active_merchants) if self._pop else cfg.initial_merchants
        loyalty_avg = (
            float(np.mean([u.loyalty_score for u in self._pop.active_users]))
            if self._pop and self._pop.active_users else 1.0
        )

        obs = np.array([
            np.clip(eco.price / cfg.initial_price, 0.0, 3.0),                  # 0
            np.clip(self._compute_volatility() / cfg.initial_price, 0.0, 1.0), # 1
            np.clip(eco._daily_tx_volume / 1_000_000, 0.0, 1.0),              # 2
            np.clip(n_users / 10_000, 0.0, 1.0),                               # 3
            float(self._sentiment.value) if self._sentiment else 0.5,          # 4
            np.clip(eco.treasury_stable / max(1.0, cfg.initial_treasury_stable), 0.0, 2.0),  # 5
            np.clip(eco.treasury_paytkn / max(1.0, cfg.initial_treasury_paytkn), 0.0, 2.0),  # 6
            np.clip(eco.total_staked / max(1.0, eco.total_supply), 0.0, 1.0), # 7
            np.clip(eco.total_supply / cfg.initial_supply - 1.0, 0.0, 1.0),   # 8
            np.clip(eco._daily_burn / max(1.0, cfg.initial_supply) * 100, 0.0, 1.0),  # 9
            np.clip(eco._reward_pool / max(1.0, cfg.initial_supply), 0.0, 0.5),       # 10
            self._day / cfg.episode_days,                                       # 11
            np.clip((n_users - self._prev_active_users) / max(1, self._prev_active_users),
                    -0.5, 0.5),                                                 # 12
            np.clip(n_merchants / 1_000, 0.0, 1.0),                            # 13
            loyalty_avg,                                                        # 14
        ], dtype=np.float32)

        return obs

    # ─────────────────────────────────────────────────────────
    # Reward
    # ─────────────────────────────────────────────────────────

    def _compute_reward(self, metrics, churned: int, n_active_u: int) -> float:
        w = self.cfg.weights
        eco = self._economy
        cfg = self.cfg

        # Positive signals
        price_growth = (eco.price - cfg.initial_price) / max(0.01, cfg.initial_price)
        treasury_growth = (
            eco.treasury_stable - self._prev_treasury_stable
        ) / max(1.0, self._prev_treasury_stable)
        retention = 1.0 - (churned / max(1, n_active_u + churned))
        tx_volume_norm = min(1.0, metrics.daily_tx_volume / 500_000)
        staking_ratio = min(1.0, eco.total_staked / max(1.0, eco.total_supply))

        positive = (
            w.price_growth * price_growth
            + w.treasury_growth * treasury_growth
            + w.user_retention * retention
            + w.tx_volume * tx_volume_norm
            + w.staking_ratio * staking_ratio
        )

        # Penalties
        volatility_penalty = self._compute_volatility() / max(0.01, cfg.initial_price)
        inflation_penalty = max(0.0, eco.total_supply / cfg.initial_supply - 1.05)
        churn_penalty = churned / max(1, n_active_u + churned)

        penalties = (
            w.volatility_penalty * volatility_penalty
            + w.inflation_penalty * inflation_penalty
            + w.churn_penalty * churn_penalty
        )

        reward = float(np.clip(positive - penalties, -10.0, 10.0))
        return reward

    # ─────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────

    def _compute_volatility(self) -> float:
        if len(self._price_history) < 2:
            return 0.0
        window = self._price_history[-7:]
        return float(np.std(window))
