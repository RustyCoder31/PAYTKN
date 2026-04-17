"""Action types representing individual user/merchant decisions within a single day.

Each Action is produced by an entity's decide_day_actions() and consumed by Economy.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class ActionKind(Enum):
    PAYMENT = "payment"         # user pays a merchant
    STAKE = "stake"             # user/merchant locks PAYTKN for yield
    UNSTAKE = "unstake"         # user/merchant removes staked tokens
    BUY = "buy"                 # buy PAYTKN from DEX with stablecoins
    SELL = "sell"               # sell PAYTKN on DEX for stablecoins
    INVITE = "invite"           # user invites a new participant
    CANCEL = "cancel"           # user cancels a subscription (loyalty decay trigger)
    LOAN_TAKE = "loan_take"     # merchant draws a collateralized loan from treasury
    LOAN_REPAY = "loan_repay"   # merchant repays outstanding loan


@dataclass
class Action:
    """A single discrete action from one entity on one day."""
    actor_id: str                   # user_id or merchant_id
    kind: ActionKind
    amount: float = 0.0             # PAYTKN units (or stablecoins for BUY)
    target_id: str | None = None    # recipient merchant (PAYMENT) or invitee id (INVITE)
