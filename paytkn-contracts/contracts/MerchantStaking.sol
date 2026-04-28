// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./PaytknToken.sol";

/**
 * @title MerchantStaking
 * @notice Separate staking pool for merchants — funded by merchant_pool_alloc
 *         slice of every payment fee. Merchants stake PAYTKN to unlock lower
 *         fees, priority settlement, and cashback boosts for their customers.
 *
 * Merchant tiers (by staked amount):
 *   Bronze  < 10,000 PAYTKN  → 0% fee discount, 0% cashback boost
 *   Silver  ≥ 10,000 PAYTKN  → 10% fee discount, 10% cashback boost
 *   Gold    ≥ 50,000 PAYTKN  → 20% fee discount, 20% cashback boost
 *   Platinum≥ 200,000 PAYTKN → 30% fee discount, 30% cashback boost
 *
 * APY is emergent: merchant_pool_balance / total_merchant_staked × 365
 * Minimum merchant pool APY enforced: 2% (anti-gaming rule)
 */
contract MerchantStaking is Ownable, ReentrancyGuard {

    PaytknToken public immutable token;

    // ── Tier thresholds (in PAYTKN, 18 decimals) ─────────────────────
    uint256 public constant SILVER_THRESHOLD   =  10_000 * 1e18;
    uint256 public constant GOLD_THRESHOLD     =  50_000 * 1e18;
    uint256 public constant PLATINUM_THRESHOLD = 200_000 * 1e18;

    uint256 public constant MIN_APY_BPS = 200; // 2% minimum APY

    // ── Merchant record ───────────────────────────────────────────────
    struct MerchantStake {
        uint256 amount;
        uint256 since;
        uint256 rewardDebt;
        bool    registered;
        uint256 totalEarned;
        uint256 paymentsProcessed;
    }

    mapping(address => MerchantStake) public merchantStakes;
    address[] public merchantList;

    // ── Pool accounting ───────────────────────────────────────────────
    uint256 public totalMerchantStaked;
    uint256 public merchantRewardPool;
    uint256 public accRewardPerShare;
    uint256 public lastRewardTime;

    uint256 private constant PRECISION = 1e18;

    // ── Stats ─────────────────────────────────────────────────────────
    uint256 public totalMerchants;
    uint256 public totalRewardsPaid;
    uint256 public totalPaymentsViaNetwork;

    // ── Events ────────────────────────────────────────────────────────
    event MerchantRegistered(address indexed merchant, uint256 stakeAmount);
    event MerchantUnstaked(address indexed merchant, uint256 amount, uint256 reward);
    event MerchantStakeIncreased(address indexed merchant, uint256 added, uint256 total);
    event MerchantPoolFunded(uint256 amount);
    event PaymentRecorded(address indexed merchant, uint256 amount);

    constructor(address _token, address admin) Ownable(admin) {
        token = PaytknToken(_token);
        lastRewardTime = block.timestamp;
    }

    // ── Fund merchant reward pool (called by Treasury) ────────────────

    function fundPool(uint256 amount) external onlyOwner {
        require(token.transferFrom(msg.sender, address(this), amount), "Transfer failed");
        merchantRewardPool += amount;
        emit MerchantPoolFunded(amount);
    }

    // ── Merchant register + stake ─────────────────────────────────────

    function registerAndStake(uint256 amount) external nonReentrant {
        require(amount > 0, "Must stake > 0");

        _updatePool();

        MerchantStake storage ms = merchantStakes[msg.sender];

        if (!ms.registered) {
            ms.registered = true;
            merchantList.push(msg.sender);
            totalMerchants++;
        }

        require(token.transferFrom(msg.sender, address(this), amount), "Transfer failed");

        // Settle pending rewards before increasing stake
        if (ms.amount > 0) {
            uint256 pending = ms.amount * accRewardPerShare / PRECISION - ms.rewardDebt;
            if (pending > 0 && merchantRewardPool >= pending) {
                merchantRewardPool -= pending;
                ms.totalEarned += pending;
                totalRewardsPaid += pending;
                require(token.transfer(msg.sender, pending), "Reward failed");
            }
        }

        ms.amount += amount;
        ms.since    = block.timestamp;
        ms.rewardDebt = ms.amount * accRewardPerShare / PRECISION;
        totalMerchantStaked += amount;

        emit MerchantRegistered(msg.sender, ms.amount);
    }

    // ── Unstake ───────────────────────────────────────────────────────

    function unstake() external nonReentrant {
        MerchantStake storage ms = merchantStakes[msg.sender];
        require(ms.amount > 0, "Nothing staked");
        require(block.timestamp >= ms.since + 7 days, "7-day lock active");

        _updatePool();

        uint256 pending = ms.amount * accRewardPerShare / PRECISION - ms.rewardDebt;
        uint256 amount  = ms.amount;

        totalMerchantStaked -= amount;
        ms.amount     = 0;
        ms.rewardDebt = 0;

        require(token.transfer(msg.sender, amount), "Transfer failed");

        if (pending > 0 && merchantRewardPool >= pending) {
            merchantRewardPool -= pending;
            ms.totalEarned += pending;
            totalRewardsPaid += pending;
            require(token.transfer(msg.sender, pending), "Reward failed");
        }

        emit MerchantUnstaked(msg.sender, amount, pending);
    }

    // ── Record payment (called by Treasury) ───────────────────────────

    function recordPayment(address merchant, uint256 amount) external onlyOwner {
        if (merchantStakes[merchant].registered) {
            merchantStakes[merchant].paymentsProcessed++;
            totalPaymentsViaNetwork++;
        }
        emit PaymentRecorded(merchant, amount);
    }

    // ── Pool update ───────────────────────────────────────────────────

    function _updatePool() internal {
        if (totalMerchantStaked == 0) {
            lastRewardTime = block.timestamp;
            return;
        }
        uint256 elapsed = block.timestamp - lastRewardTime;
        if (elapsed == 0) return;

        uint256 dailyRate    = merchantRewardPool / 365;
        // Enforce minimum 2% APY
        uint256 minDaily     = totalMerchantStaked * MIN_APY_BPS / 10000 / 365;
        uint256 effective    = dailyRate < minDaily ? minDaily : dailyRate;
        uint256 toDistribute = effective * elapsed / 1 days;
        if (toDistribute > merchantRewardPool) toDistribute = merchantRewardPool;

        if (toDistribute > 0) {
            accRewardPerShare += toDistribute * PRECISION / totalMerchantStaked;
            merchantRewardPool -= toDistribute;
        }
        lastRewardTime = block.timestamp;
    }

    // ── View: merchant tier ───────────────────────────────────────────

    function getMerchantTier(address merchant)
        external view returns (
            uint8  tier,           // 0=Bronze 1=Silver 2=Gold 3=Platinum
            uint256 feeDiscountBps,
            uint256 cashbackBoostBps
        )
    {
        uint256 staked = merchantStakes[merchant].amount;
        if (staked >= PLATINUM_THRESHOLD) return (3, 3000, 3000);
        if (staked >= GOLD_THRESHOLD)     return (2, 2000, 2000);
        if (staked >= SILVER_THRESHOLD)   return (1, 1000, 1000);
        return (0, 0, 0);
    }

    function getMerchantInfo(address merchant)
        external view returns (MerchantStake memory)
    {
        return merchantStakes[merchant];
    }

    function currentAPY() external view returns (uint256) {
        if (totalMerchantStaked == 0) return 0;
        return merchantRewardPool * 10000 / totalMerchantStaked;
    }

    function getMerchantCount() external view returns (uint256) {
        return totalMerchants;
    }

    function pendingReward(address merchant) external view returns (uint256) {
        MerchantStake memory ms = merchantStakes[merchant];
        if (ms.amount == 0) return 0;
        uint256 _accRPS = accRewardPerShare;
        if (totalMerchantStaked > 0) {
            uint256 elapsed      = block.timestamp - lastRewardTime;
            uint256 toDistribute = (merchantRewardPool / 365) * elapsed / 1 days;
            if (toDistribute > merchantRewardPool) toDistribute = merchantRewardPool;
            _accRPS += toDistribute * PRECISION / totalMerchantStaked;
        }
        return ms.amount * _accRPS / PRECISION - ms.rewardDebt;
    }
}
