// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "./PaytknToken.sol";
import "./PaytknStaking.sol";
import "./MerchantStaking.sol";

/**
 * @title RewardEngine
 * @notice Tx Reward Engine — calculates amplified cashback for every payment.
 *
 * Cashback formula (from PAYTKN tokenomics Sheet 7):
 *   effective_cashback = base_rate
 *     × (1 + loyalty_boost)       ← time as user (max +100%)
 *     × (1 + staking_boost)       ← PAYTKN staked (max +50%)
 *     × (1 + seniority_boost)     ← account age (max +30%)
 *     × (1 + invite_boost)        ← referral depth (max +20%)
 *
 * Anti-gaming rules enforced here:
 *   - Cancel limit: max 3 per week (loyalty decay on cancel)
 *   - Invite depth: max 5 levels
 *   - Tx staking delay: 7 days after stake before boost applies
 *
 * The engine is READ-ONLY for calculation — actual minting done by Treasury.
 */
contract RewardEngine is Ownable {

    PaytknToken     public immutable token;
    PaytknStaking   public immutable staking;
    MerchantStaking public immutable merchantStaking;

    // ── Anti-gaming caps (from AntiGamingRules in config.py) ──────────
    uint256 public constant MAX_LOYALTY_BOOST_BPS   = 10000; // +100%
    uint256 public constant MAX_STAKING_BOOST_BPS   =  5000; // +50%
    uint256 public constant MAX_SENIORITY_BOOST_BPS =  3000; // +30%
    uint256 public constant MAX_INVITE_BOOST_BPS    =  2000; // +20%

    uint256 public constant CANCEL_LIMIT_PER_WEEK = 3;
    uint256 public constant INVITE_DEPTH_MAX       = 5;
    uint256 public constant STAKING_DELAY_DAYS     = 7;
    uint256 public constant LOYALTY_DECAY_PER_CANCEL_BPS = 1000; // 10% decay

    // ── User profile ──────────────────────────────────────────────────
    struct UserProfile {
        uint256 joinedAt;           // timestamp of first transaction
        uint256 loyaltyScore;       // 0–10000 bps, grows with activity
        uint256 cancelsThisWeek;
        uint256 cancelWeekStart;
        uint256 inviteDepth;        // 0–5
        uint256 totalTransactions;
        address invitedBy;
        bool    registered;
    }

    mapping(address => UserProfile) public profiles;

    // ── Events ────────────────────────────────────────────────────────
    event UserRegistered(address indexed user, address indexed invitedBy);
    event LoyaltyUpdated(address indexed user, uint256 newScore);
    event CancelRecorded(address indexed user, uint256 cancelsThisWeek);

    constructor(
        address _token,
        address _staking,
        address _merchantStaking,
        address admin
    ) Ownable(admin) {
        token           = PaytknToken(_token);
        staking         = PaytknStaking(_staking);
        merchantStaking = MerchantStaking(_merchantStaking);
    }

    // ── User registration ─────────────────────────────────────────────

    function registerUser(address user, address invitedBy) external onlyOwner {
        require(!profiles[user].registered, "Already registered");
        uint256 depth = 0;
        if (invitedBy != address(0) && profiles[invitedBy].registered) {
            depth = profiles[invitedBy].inviteDepth + 1;
            if (depth > INVITE_DEPTH_MAX) depth = INVITE_DEPTH_MAX;
        }
        profiles[user] = UserProfile({
            joinedAt:          block.timestamp,
            loyaltyScore:      0,
            cancelsThisWeek:   0,
            cancelWeekStart:   block.timestamp,
            inviteDepth:       depth,
            totalTransactions: 0,
            invitedBy:         invitedBy,
            registered:        true
        });
        emit UserRegistered(user, invitedBy);
    }

    // ── Calculate cashback ────────────────────────────────────────────

    /**
     * @notice Calculate effective cashback in PAYTKN for a given payment.
     * @param user          Customer wallet
     * @param merchant      Merchant wallet
     * @param paymentAmount Payment amount in wei (ETH stand-in)
     * @param baseCashbackBps Base cashback rate from token parameters
     * @return cashbackPAYTKN Amount of PAYTKN to mint as cashback
     * @return effectiveRateBps The final amplified cashback rate in bps
     */
    function calculateCashback(
        address user,
        address merchant,
        uint256 paymentAmount,
        uint256 baseCashbackBps,
        uint256 paytknPriceUsd  // scaled 1e8
    ) external view returns (
        uint256 cashbackPAYTKN,
        uint256 effectiveRateBps
    ) {
        UserProfile memory up = profiles[user];

        // ── Loyalty boost (time as active user) ───────────────────────
        uint256 loyaltyBoost = 0;
        if (up.registered) {
            // Grows with loyalty score: max +100% at score 10000
            loyaltyBoost = up.loyaltyScore * MAX_LOYALTY_BOOST_BPS / 10000;
        }

        // ── Staking boost (must be staked for ≥ 7 days) ──────────────
        uint256 stakingBoost = 0;
        uint256 numStakes    = staking.stakeCount(user);
        if (numStakes > 0) {
            PaytknStaking.Stake[] memory userStakes = staking.getStakes(user);
            uint256 eligibleStaked = 0;
            for (uint256 i = 0; i < userStakes.length; i++) {
                if (userStakes[i].amount > 0 &&
                    block.timestamp >= userStakes[i].since + STAKING_DELAY_DAYS * 1 days)
                {
                    eligibleStaked += userStakes[i].amount;
                }
            }
            uint256 supply = token.totalSupply();
            if (supply > 0) {
                // Boost scales with staked fraction of supply (cap at MAX)
                uint256 stakedFraction = eligibleStaked * 10000 / supply;
                stakingBoost = stakedFraction * MAX_STAKING_BOOST_BPS / 10000;
                if (stakingBoost > MAX_STAKING_BOOST_BPS)
                    stakingBoost = MAX_STAKING_BOOST_BPS;
            }
        }

        // ── Seniority boost (account age) ────────────────────────────
        uint256 seniorityBoost = 0;
        if (up.registered && up.joinedAt > 0) {
            uint256 ageMonths = (block.timestamp - up.joinedAt) / 30 days;
            // Max boost at 12 months
            seniorityBoost = ageMonths * MAX_SENIORITY_BOOST_BPS / 12;
            if (seniorityBoost > MAX_SENIORITY_BOOST_BPS)
                seniorityBoost = MAX_SENIORITY_BOOST_BPS;
        }

        // ── Invite boost (referral depth) ─────────────────────────────
        uint256 inviteBoost = 0;
        if (up.registered) {
            inviteBoost = up.inviteDepth * MAX_INVITE_BOOST_BPS / INVITE_DEPTH_MAX;
        }

        // ── Merchant cashback boost ───────────────────────────────────
        (, , uint256 merchantBoostBps) = merchantStaking.getMerchantTier(merchant);

        // ── Compound all boosts ───────────────────────────────────────
        // effective = base × (1 + loyalty) × (1 + staking) × (1 + seniority) × (1 + invite)
        // Using sequential multiplication to avoid overflow
        uint256 rate = baseCashbackBps;
        rate = rate * (10000 + loyaltyBoost)   / 10000;
        rate = rate * (10000 + stakingBoost)   / 10000;
        rate = rate * (10000 + seniorityBoost) / 10000;
        rate = rate * (10000 + inviteBoost)    / 10000;
        rate = rate * (10000 + merchantBoostBps) / 10000;

        // Hard cap: base × 3 (prevents runaway cashback from all boosts)
        uint256 maxRate = baseCashbackBps * 3;
        if (rate > maxRate) rate = maxRate;

        effectiveRateBps = rate;

        // Convert to PAYTKN amount
        uint256 cashbackEth = paymentAmount * rate / 10000;
        cashbackPAYTKN = cashbackEth * 1e8 / paytknPriceUsd;
    }

    // ── Record transaction (updates loyalty) ──────────────────────────

    function recordTransaction(address user) external onlyOwner {
        UserProfile storage up = profiles[user];
        if (!up.registered) return;

        up.totalTransactions++;

        // Loyalty grows 100 bps per transaction, capped at 10000
        if (up.loyaltyScore < 10000) {
            up.loyaltyScore += 100;
            if (up.loyaltyScore > 10000) up.loyaltyScore = 10000;
        }

        emit LoyaltyUpdated(user, up.loyaltyScore);
    }

    // ── Record cancel (anti-gaming) ───────────────────────────────────

    function recordCancel(address user) external onlyOwner {
        UserProfile storage up = profiles[user];
        if (!up.registered) return;

        // Reset weekly counter if new week
        if (block.timestamp >= up.cancelWeekStart + 7 days) {
            up.cancelsThisWeek = 0;
            up.cancelWeekStart = block.timestamp;
        }

        require(up.cancelsThisWeek < CANCEL_LIMIT_PER_WEEK, "Cancel limit reached");
        up.cancelsThisWeek++;

        // Loyalty decay on cancel
        uint256 decay = up.loyaltyScore * LOYALTY_DECAY_PER_CANCEL_BPS / 10000;
        up.loyaltyScore = up.loyaltyScore > decay ? up.loyaltyScore - decay : 0;

        emit CancelRecorded(user, up.cancelsThisWeek);
        emit LoyaltyUpdated(user, up.loyaltyScore);
    }

    // ── View helpers ──────────────────────────────────────────────────

    function getUserProfile(address user)
        external view returns (UserProfile memory)
    {
        return profiles[user];
    }

    function getUserBoosts(address user) external view returns (
        uint256 loyaltyBoostBps,
        uint256 seniorityBoostBps,
        uint256 inviteBoostBps
    ) {
        UserProfile memory up = profiles[user];
        if (!up.registered) return (0, 0, 0);

        loyaltyBoostBps = up.loyaltyScore * MAX_LOYALTY_BOOST_BPS / 10000;

        uint256 ageMonths = (block.timestamp - up.joinedAt) / 30 days;
        seniorityBoostBps = ageMonths * MAX_SENIORITY_BOOST_BPS / 12;
        if (seniorityBoostBps > MAX_SENIORITY_BOOST_BPS)
            seniorityBoostBps = MAX_SENIORITY_BOOST_BPS;

        inviteBoostBps = up.inviteDepth * MAX_INVITE_BOOST_BPS / INVITE_DEPTH_MAX;
    }
}
