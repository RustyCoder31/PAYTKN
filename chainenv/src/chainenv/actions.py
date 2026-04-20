"""Action types representing individual user/merchant decisions within a single day.

Each Action is produced by an entity's decide_day_actions() and consumed by Economy.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class ActionKind(Enum):
    PAYMENT = "payment"               # user pays a merchant
    STAKE = "stake"                   # user/merchant buys PAYTKN and locks for yield
    UNSTAKE = "unstake"               # user removes staked tokens → stable
    MERCHANT_STAKE = "merchant_stake" # merchant stakes wallet_paytkn → merchant staking pool
    BUY = "buy"                       # speculative buy PAYTKN via AMM with stable
    IN_APP_BUY = "in_app_buy"         # buy PAYTKN directly from treasury (slight discount, no AMM impact)
    SELL = "sell"                     # sell PAYTKN for stable (user speculative or merchant holdings)
    INVITE = "invite"                 # user invites a new participant
    CANCEL = "cancel"                 # user cancels a subscription (loyalty decay trigger)


@dataclass
class Action:
    """A single discrete action from one entity on one day."""
    actor_id: str                   # user_id or merchant_id
    kind: ActionKind
    amount: float = 0.0             # PAYTKN units (or stablecoins for BUY)
    target_id: str | None = None    # recipient merchant (PAYMENT) or invitee id (INVITE)
