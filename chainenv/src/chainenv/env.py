"""PaytknEnv — Gymnasium environment, v3.1 payment-utility architecture.

Diagram-aligned. Merchant receives PAYTKN and holds (decides when to sell).
Cashback uses Tx Reward Engine: loyalty × staking_boost × seniority × invite_tier.
Merchant staking pool: separate from user staking, funded by tx fee slice.
Burn: RL-controlled daily burn from treasury (NOT from payment fees).
Mint: adaptive — scales with ecosystem tx growth, penalised by inflation/price drop.

Observation space (20-dim):
  0  price_ratio           current_price / 1.00 (clipped 0–3)
  1  volatility_norm       7-day price std / 1.00 (clipped 0–1)
  2  tx_volume_norm        daily payment USD / 500_000
  3  active_users_norm     active_users / 50_000
  4  sentiment             [0, 1]
  5  treasury_stable_norm  treasury_stable / initial_stable (clipped 0–3)
  6  treasury_paytkn_norm  treasury_paytkn * price / initial_stable (clipped 0–3)
  7  staking_ratio         total_staked_USD / total_supply_USD (clipped 0–1)
  8  supply_inflation      total_supply / initial_supply - 1 (clipped 0–1)
  9  reward_pool_norm      reward_pool * price / initial_stable (clipped 0–0.5)
 10  day_norm              day / episode_days
 11  user_growth_rate      (users - prev_users) / max(1, prev_users) clipped +-0.5
 12  merchant_count_norm   active_merchants / 5_000
 13  loyalty_avg           mean user loyalty [0, 1]
 14  lp_depth_norm         lp_depth_stable / min_lp_depth_stable (clipped 0–5)
 15  lp_provider_count_norm active_lps / 50
 16  avg_il_norm           average IL across LPs (clipped 0–0.3)
 17  actual_apy_norm       actual APY / 0.30 (clipped 0–1)
 18  daily_fees_norm       daily_fees_collected / 50_000
 19  merchant_pool_norm    merchant_staking_pool / initial_stable (clipped 0–1)

Action space (6-dim, all in [-1, 1]):
  0  mint_factor           -> [0.0,   2.0]    adaptive mint multiplier
  1  burn_rate             -> [0.0,   0.003]  daily burn fraction of treasury PAYTKN
  2  reward_alloc          -> [0.20,  0.60]   fraction of fees to user reward pool
  3  cashback_base_rate    -> [0.001, 0.010]  base cashback fraction (fees are primary revenue)
  4  merchant_pool_alloc   -> [0.05,  0.25]   fraction of fees to merchant staking pool
  5  treasury_ratio        -> [0.50,  0.90]   treasury stable fraction target

LP bonuses removed — LPs earn from 0.3% swap fees naturally.
Loans removed — not needed at this stage.
"""

from __future__ import annotations
import numpy as np
import gymnasium as gym
from gymnasium import spaces

from chainenv.config import SimConfig, map_action
from chainenv.economy import Economy, EconomyMetrics
from chainenv.sentiment import MarketSentiment
from chainenv.population import PopulationManager
from chainenv.actions import ActionKind


OBS_DIM = 20
ACT_DIM = 6


class PaytknEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, cfg: SimConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg or SimConfig()

        self.observation_space = spaces.Box(
            low=-1.0, high=5.0, shape=(OBS_DIM,), dtype=np.float32,
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(ACT_DIM,), dtype=np.float32,
        )

        self._economy: Economy | None = None
        self._sentiment: MarketSentiment | None = None
        self._pop: PopulationManager | None = None
        self._rng: np.random.Generator | None = None
        self._day: int = 0
        self._price_history: list[float] = []
        self._prev_active_users: int = 0
        self._prev_treasury_stable: float = 0.0
        self._last_actual_apy: float = 0.03
        self._episode_metrics: list[dict] = []

    # ─────────────────────────────────────────────────────────
    # Gymnasium API
    # ─────────────────────────────────────────────────────────

    def reset(self, *, seed: int | None = None, options: dict | None = None):
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
        self._pop.seed_initial(initial_price=self.cfg.initial_price)

        self._day = 0
        self._price_history = [self.cfg.initial_price]
        self._prev_active_users = self.cfg.initial_users
        self._prev_treasury_stable = self.cfg.initial_treasury_stable
        self._last_actual_apy = self.cfg.rules.min_staking_apy
        self._episode_metrics = []
        self._cached_volatility = 0.0

        return self._get_obs(), {}

    def step(self, action: np.ndarray):
        assert self._economy is not None, "Call reset() first."
        eco = self._economy
        b = self.cfg.bounds

        # 1. Agent levers (6-dim)
        eco.apply_agent_levers(
            mint_factor=         map_action(float(action[0]), *b.mint_factor),
            burn_rate=           map_action(float(action[1]), *b.burn_rate),
            reward_alloc=        map_action(float(action[2]), *b.reward_alloc),
            cashback_base_rate=  map_action(float(action[3]), *b.cashback_base_rate),
            merchant_pool_alloc= map_action(float(action[4]), *b.merchant_pool_alloc),
            treasury_ratio=      map_action(float(action[5]), *b.treasury_ratio),
        )

        # 2. Begin day
        eco.begin_day()
        self._day += 1

        # 3. Population churn pressure + organic growth
        price_ratio = eco.price / max(0.001, self.cfg.initial_price)
        new_u, churned = self._pop.daily_update(
            sentiment=self._sentiment.value,
            actual_apy=self._last_actual_apy,
            price=eco.price,
            price_ratio=price_ratio,
        )

        if self._day % 7 == 0:
            self._pop.weekly_reset()

        # 4. Entity actions → economy
        active_merchants = self._pop.active_merchants
        active_users     = self._pop.active_users

        # Build merchant lookup for O(1) access
        merchant_map = {m.merchant_id: m for m in active_merchants}

        # Batch-roll recurring_factor check — one rng call instead of one per user
        n_u = len(active_users)
        if n_u > 0:
            act_rolls = self._rng.random(n_u)
            for user, roll in zip(active_users, act_rolls):
                if roll > user.profile.recurring_factor:
                    user.days_active += 1   # still ages even if no action today
                    continue
                u_actions = user.decide_day_actions(
                    rng=self._rng,
                    sentiment=self._sentiment.value,
                    price=eco.price,
                    actual_apy=self._last_actual_apy,
                    rules=self.cfg.rules,
                    merchants=active_merchants,
                )
                self._process_user_actions(u_actions, user, merchant_map, eco)

        for merchant in active_merchants:
            m_actions = merchant.decide_day_actions(
                rng=self._rng,
                sentiment=self._sentiment.value,
                price=eco.price,
                actual_apy=self._last_actual_apy,
                rules=self.cfg.rules,
            )
            self._process_merchant_actions(m_actions, merchant, eco)

        # 5. End day
        n_active_u = len(active_users)
        n_active_m = len(active_merchants)
        metrics, actual_apy = eco.end_day(
            active_users=n_active_u,
            active_merchants=n_active_m,
            lp_providers=self._pop.lp_providers,
        )
        self._last_actual_apy = actual_apy

        # 6. LP lifecycle
        treasury_solvent = eco.treasury_stable > 50_000
        self._pop.daily_update_lp_providers(
            current_price=eco.price,
            daily_fees_to_lps=metrics.daily_fees_to_lps,
            treasury_covers_il=treasury_solvent,
        )

        # 7. Sentiment — cache volatility once (used in sentiment, obs, reward)
        self._cached_volatility = self._compute_volatility()
        volatility = self._cached_volatility
        treasury_health = eco.treasury_stable / max(1.0, self.cfg.initial_treasury_stable)
        self._sentiment.update(
            price=eco.price,
            price_yesterday=self._price_history[-1],
            volatility=volatility,
            treasury_health=treasury_health,
            active_users=n_active_u,
            prev_users=self._prev_active_users,
        )
        self._price_history.append(eco.price)

        # 8. Reward
        reward = self._compute_reward(metrics, churned, n_active_u)

        # 9. Log
        self._episode_metrics.append({
            "day":                    self._day,
            "price":                  eco.price,
            "sentiment":              self._sentiment.value,
            "active_users":           n_active_u,
            "active_merchants":       n_active_m,
            "active_lp_providers":    len(self._pop.active_lp_providers),
            "treasury_stable":        eco.treasury_stable,
            "treasury_paytkn":        eco.treasury_paytkn,
            "total_supply":           eco.total_supply,
            "total_staked":           eco.total_staked,
            "merchant_staked":        eco.merchant_staked,
            "actual_apy":             actual_apy,
            "merchant_pool_apy":      metrics.merchant_pool_apy,
            "lp_depth_stable":        metrics.lp_depth_stable,
            "avg_il":                 metrics.avg_il,
            "tx_volume":              metrics.daily_tx_volume,
            "payment_count":          metrics.daily_payment_count,
            "daily_fees_collected":   metrics.daily_fees_collected,
            "daily_fees_to_lps":      metrics.daily_fees_to_lps,
            "daily_rewards_paid":     metrics.daily_rewards_paid,
            "daily_cashback_paid":    metrics.daily_cashback_paid,
            "daily_merchant_rewards": metrics.daily_merchant_rewards,
            "merchant_staking_pool":  metrics.merchant_staking_pool,
            "cumulative_rewards_paid":metrics.cumulative_rewards_paid,
            "cumulative_tx_volume":   metrics.cumulative_tx_volume,
            "daily_burn":             metrics.daily_burn,
            "daily_mint":             metrics.daily_mint,
            "daily_in_app_volume":    metrics.daily_in_app_volume,
            "daily_dev_fees":         metrics.daily_dev_fees,
            "reward":                 reward,
        })

        # 10. Update trackers
        self._prev_active_users    = n_active_u
        self._prev_treasury_stable = eco.treasury_stable

        terminated = self._day >= self.cfg.episode_days
        return self._get_obs(), reward, terminated, False, {"metrics": metrics}

    # ─────────────────────────────────────────────────────────
    # Action processing
    # ─────────────────────────────────────────────────────────

    def _process_user_actions(self, actions, user, merchant_map: dict, eco: Economy) -> None:
        for act in actions:
            if act.kind == ActionKind.PAYMENT and act.target_id:
                # Tx Reward Engine boosts (from user attributes, per diagram)
                stk_boost = user.staking_boost(eco.price)
                sen_boost = user.seniority_boost()
                inv_boost = user.invite_boost()

                paytkn_to_merchant, cashback_paytkn = eco.process_payment(
                    payer_id=act.actor_id,
                    merchant_id=act.target_id,
                    amount_usd=act.amount,
                    loyalty_score=user.loyalty_score,
                    staking_boost=stk_boost,
                    seniority_boost=sen_boost,
                    invite_boost=inv_boost,
                )
                # Merchant receives PAYTKN (holds, decides when to sell)
                merchant = merchant_map.get(act.target_id)
                if merchant:
                    merchant.receive_payment_paytkn(paytkn_to_merchant, eco.price)
                # Cashback to user in PAYTKN → added to staked (reward for paying)
                if cashback_paytkn > 0:
                    user.staked += cashback_paytkn
                    eco.record_stake(cashback_paytkn)

            elif act.kind == ActionKind.STAKE:
                # User buys PAYTKN with stable → locks it
                paytkn_acquired = eco.execute_buy(act.actor_id, act.amount)
                eco.record_stake(paytkn_acquired)
                user.staked += paytkn_acquired  # wallet already debited in decide_day_actions

            elif act.kind == ActionKind.UNSTAKE:
                # User sells PAYTKN → gets stable
                stable_received = eco.execute_sell(act.actor_id, act.amount)
                eco.record_unstake(act.amount)
                user.receive_unstake_proceeds(stable_received)

            elif act.kind == ActionKind.IN_APP_BUY:
                # Buy PAYTKN directly from treasury (slight discount, no AMM impact)
                if user.wallet >= act.amount:
                    paytkn = eco.execute_in_app_buy(
                        act.actor_id, act.amount,
                        actor_current_paytkn=user.staked,
                    )
                    if paytkn > 0:
                        stable_paid = paytkn * eco.price * (1.0 - eco.cfg.rules.in_app_discount_rate)
                        user.wallet -= min(stable_paid, user.wallet)
                        user.staked += paytkn

            elif act.kind == ActionKind.BUY:
                # Speculative buy via AMM with stable
                if user.wallet >= act.amount:
                    paytkn = eco.execute_buy(act.actor_id, act.amount)
                    user.wallet -= act.amount
                    user.staked += paytkn   # speculative buys add to staked pool

            elif act.kind == ActionKind.SELL:
                # Speculative sell of staked PAYTKN
                if user.staked >= act.amount:
                    stable = eco.execute_sell(act.actor_id, act.amount)
                    user.staked -= act.amount
                    user.wallet += stable

    def _process_merchant_actions(self, actions, merchant, eco: Economy) -> None:
        for act in actions:
            if act.kind == ActionKind.SELL:
                # Merchant sells free PAYTKN (wallet_paytkn) for stable
                # wallet_paytkn already debited in decide_day_actions
                stable_received = eco.execute_sell(act.actor_id, act.amount)
                merchant.wallet += stable_received

            elif act.kind == ActionKind.MERCHANT_STAKE:
                # Merchant stakes free PAYTKN into merchant staking pool
                # wallet_paytkn already debited in decide_day_actions
                eco.record_merchant_stake(act.amount)
                merchant.staked += act.amount

            elif act.kind == ActionKind.STAKE:
                # Merchant buys PAYTKN with stable → merchant staking pool
                paytkn = eco.execute_buy(act.actor_id, act.amount)
                eco.record_merchant_stake(paytkn)
                merchant.staked += paytkn

    # ─────────────────────────────────────────────────────────
    # Observation (20-dim)
    # ─────────────────────────────────────────────────────────

    def _get_obs(self) -> np.ndarray:
        eco = self._economy
        cfg = self.cfg

        if eco is None:
            return np.zeros(OBS_DIM, dtype=np.float32)

        n_users     = len(self._pop.active_users)     if self._pop else cfg.initial_users
        n_merchants = len(self._pop.active_merchants) if self._pop else cfg.initial_merchants
        n_lps       = len(self._pop.active_lp_providers) if self._pop else 0

        # Running mean maintained by PopulationManager — no list comprehension
        loyalty_avg = self._pop.loyalty_avg if self._pop else 1.0

        # Staking ratio in USD terms
        staked_usd   = eco.total_staked * eco.price
        supply_usd   = eco.total_supply * eco.price
        staking_ratio = staked_usd / max(1.0, supply_usd)

        reward_pool_usd = eco._reward_pool * eco.price

        obs = np.array([
            np.clip(eco.price / cfg.initial_price, 0.0, 3.0),                                  # 0
            np.clip(self._cached_volatility / max(0.001, cfg.initial_price), 0.0, 1.0),        # 1
            np.clip(eco._daily_tx_volume / 500_000, 0.0, 1.0),                                 # 2
            np.clip(n_users / 50_000, 0.0, 1.0),                                               # 3
            float(self._sentiment.value) if self._sentiment else 0.5,                          # 4
            np.clip(eco.treasury_stable / max(1.0, cfg.initial_treasury_stable), 0.0, 3.0),   # 5
            np.clip(eco.treasury_paytkn * eco.price / max(1.0, cfg.initial_treasury_stable), 0.0, 3.0),  # 6
            np.clip(staking_ratio, 0.0, 1.0),                                                  # 7
            np.clip(eco.total_supply / cfg.initial_supply - 1.0, 0.0, 1.0),                   # 8
            np.clip(reward_pool_usd / max(1.0, cfg.initial_treasury_stable), 0.0, 0.5),        # 9
            self._day / cfg.episode_days,                                                       # 10
            np.clip(
                (n_users - self._prev_active_users) / max(1, self._prev_active_users),
                -0.5, 0.5,
            ),                                                                                  # 11
            np.clip(n_merchants / 5_000, 0.0, 1.0),                                            # 12
            float(np.clip(loyalty_avg, 0.0, 1.0)),                                             # 13
            np.clip(eco.lp_depth_stable / max(1.0, cfg.rules.min_lp_depth_stable), 0.0, 5.0), # 14
            np.clip(n_lps / 50, 0.0, 1.0),                                                     # 15
            np.clip(eco._daily_fees_to_lps / max(1.0, eco.lp_depth_stable) * 100, 0.0, 0.3), # 16 avg_il proxy
            np.clip(self._last_actual_apy / 0.30, 0.0, 1.0),                                  # 17
            np.clip(eco._daily_fees_collected / 50_000, 0.0, 1.0),                             # 18
            np.clip(eco._merchant_staking_pool / max(1.0, cfg.initial_treasury_stable), 0.0, 1.0),  # 19
        ], dtype=np.float32)

        return obs

    # ─────────────────────────────────────────────────────────
    # Reward — treasury health first
    # ─────────────────────────────────────────────────────────

    def _compute_reward(
        self,
        metrics: EconomyMetrics,
        churned: int,
        n_active_u: int,
    ) -> float:
        w   = self.cfg.weights
        eco = self._economy
        cfg = self.cfg
        prev_u = self._prev_active_users

        # ── 1. Treasury health (PRIMARY) ──────────────────────
        # Stable: scored 0→1 from floor to initial, capped at 1
        floor   = cfg.rules.treasury_stable_floor
        stable_score = float(np.clip(
            (eco.treasury_stable - floor) / max(1.0, cfg.initial_treasury_stable - floor),
            0.0, 1.0,
        ))
        # PAYTKN: scored 0→1 once it reaches 50% of initial_stable in USD value
        tsy_paytkn_usd = eco.treasury_paytkn * max(0.001, eco.price)
        paytkn_score   = float(np.clip(
            tsy_paytkn_usd / max(1.0, cfg.initial_treasury_stable * 0.50),
            0.0, 1.0,
        ))
        treasury_signal = 0.65 * stable_score + 0.35 * paytkn_score

        # ── 2. APY signal ─────────────────────────────────────
        # Reward APY in the sweet spot 8–20%. Too low = people leave, too high = unsustainable.
        # Hard penalty above 25%: 100%+ APY attracts mercenary capital, not real users.
        apy = self._last_actual_apy
        if 0.08 <= apy <= 0.20:
            apy_score = 1.0
        elif apy < 0.08:
            apy_score = float(np.clip(apy / 0.08, 0.0, 1.0))
        else:
            # Linearly decays: 0.20 → 1.0, 0.50 → 0.0, >0.50 → 0.0
            apy_score = float(np.clip(1.0 - (apy - 0.20) / 0.30, 0.0, 1.0))
        apy_signal = apy_score

        # Over-APY penalty: fires when APY > 25%, scales up aggressively above that
        # Gives RL a clear signal to reduce reward_alloc when APY is excessive
        apy_over_penalty = float(np.clip((apy - 0.25) / 0.25, 0.0, 1.0)) if apy > 0.25 else 0.0

        # ── 3. User growth ────────────────────────────────────
        user_delta = (n_active_u - prev_u) / max(1.0, prev_u)
        user_growth_signal = float(np.clip(user_delta * 5.0 + 0.5, 0.0, 1.0))

        # ── 4. Stability ──────────────────────────────────────
        price_deviation = abs(eco.price - cfg.rules.price_target) / cfg.rules.price_target
        price_stable    = float(np.clip(1.0 - price_deviation / cfg.rules.price_band_pct, 0.0, 1.0))
        vol             = self._cached_volatility / max(0.001, cfg.initial_price)
        vol_stable      = float(np.clip(1.0 - vol * 5.0, 0.0, 1.0))
        sentiment_ok    = float(np.clip(self._sentiment.value * 1.3, 0.0, 1.0))
        stability_signal = 0.4 * price_stable + 0.3 * vol_stable + 0.3 * sentiment_ok

        # ── 5. TX volume ──────────────────────────────────────
        tx_signal = float(np.clip(metrics.daily_tx_volume / 100_000, 0.0, 1.0))

        # ── 6. LP depth ───────────────────────────────────────
        lp_ratio  = eco.lp_depth_stable / max(1.0, cfg.rules.min_lp_depth_stable)
        lp_signal = float(np.clip((lp_ratio - 1.0) / 4.0 + 0.5, 0.0, 1.0))

        # ── 7. Price growth (controlled) ──────────────────────
        price_ratio = eco.price / cfg.initial_price
        if 0.85 <= price_ratio <= 1.50:
            price_signal = float(np.clip((price_ratio - 0.85) / 0.65, 0.0, 1.0))
        else:
            price_signal = max(0.0, 1.0 - abs(price_ratio - 1.175) / 1.0)

        positive = (
            w.treasury_health * treasury_signal
            + w.user_growth   * user_growth_signal
            + w.stability     * stability_signal
            + w.tx_volume     * tx_signal
            + w.apy_signal    * apy_signal
            + w.lp_depth      * lp_signal
            + w.price_growth  * price_signal
        )

        # ── Penalties ─────────────────────────────────────────

        # Treasury floor breach — hard penalty (primary constraint)
        stable_deficit   = max(0.0, floor - eco.treasury_stable)
        floor_frac       = stable_deficit / max(1.0, floor)
        treasury_floor_signal = float(np.clip(floor_frac * 3.0, 0.0, 1.0))

        # Treasury PAYTKN cap breach — mild nudge to burn/redistribute
        cap_usd          = cfg.rules.treasury_paytkn_cap_ratio * cfg.initial_treasury_stable
        cap_breach_frac  = max(0.0, tsy_paytkn_usd - cap_usd) / max(1.0, cap_usd)
        treasury_cap_signal = float(np.clip(cap_breach_frac * 2.0, 0.0, 1.0))

        churn_frac   = churned / max(1.0, n_active_u + churned)
        churn_signal = float(np.clip(churn_frac * 5.0, 0.0, 1.0))

        vol_signal   = float(np.clip(vol * 3.0, 0.0, 1.0))

        inflation    = max(0.0, eco.total_supply / cfg.initial_supply - 1.02)
        inflation_signal = float(np.clip(inflation * 20.0, 0.0, 1.0))

        penalties = (
            w.treasury_floor_penalty * treasury_floor_signal
            + w.treasury_cap_penalty * treasury_cap_signal
            + w.churn_penalty        * churn_signal
            + w.volatility_penalty   * vol_signal
            + w.inflation_penalty    * inflation_signal
            + w.apy_signal           * apy_over_penalty   # reuse apy weight — penalise runaway APY
        )

        return float(np.clip(positive - penalties, -5.0, 5.0))

    def _compute_volatility(self) -> float:
        if len(self._price_history) < 2:
            return 0.0
        return float(np.std(self._price_history[-7:]))
