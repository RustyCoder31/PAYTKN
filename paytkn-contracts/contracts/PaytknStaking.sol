// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./PaytknToken.sol";

/**
 * @title PaytknStaking
 * @notice Users stake PAYTKN to earn rewards.
 *         APY is emergent: reward_pool_balance / total_staked * 365.
 *         Rewards are funded by the Treasury routing fee income here.
 *
 * Lockup tiers (days -> APY boost multiplier in bps):
 *   Flexible  (0d)  -> 1.0x
 *   30 days         -> 1.2x
 *   90 days         -> 1.5x
 *   180 days        -> 2.0x
 */
contract PaytknStaking is Ownable, ReentrancyGuard {

    PaytknToken public immutable token;

    // ── Lockup tiers ──────────────────────────────────────────────────
    uint256[] public lockupDurations = [0, 30 days, 90 days, 180 days];
    uint256[] public lockupMultipliers = [10000, 12000, 15000, 20000]; // bps (1x, 1.2x, 1.5x, 2x)

    // ── Stake record ──────────────────────────────────────────────────
    struct Stake {
        uint256 amount;
        uint256 since;       // timestamp of stake
        uint256 lockupEnd;   // earliest unstake time
        uint256 multiplier;  // lockup multiplier in bps
        uint256 rewardDebt;  // reward accounting
    }

    mapping(address => Stake[]) public stakes;

    // ── Pool accounting ───────────────────────────────────────────────
    uint256 public totalStaked;
    uint256 public rewardPool;           // PAYTKN funded by Treasury
    uint256 public accRewardPerShare;    // accumulated reward per staked token (scaled 1e18)
    uint256 public lastRewardTime;

    uint256 private constant PRECISION = 1e18;

    // ── Stats ─────────────────────────────────────────────────────────
    uint256 public totalRewardsClaimed;
    uint256 public uniqueStakers;
    mapping(address => bool) public hasStaked;

    // ── Events ────────────────────────────────────────────────────────
    event Staked(address indexed user, uint256 amount, uint256 lockupDays, uint256 stakeIndex);
    event Unstaked(address indexed user, uint256 amount, uint256 reward, uint256 stakeIndex);
    event RewardFunded(uint256 amount);
    event RewardClaimed(address indexed user, uint256 amount);

    constructor(address _token, address admin) Ownable(admin) {
        token = PaytknToken(_token);
        lastRewardTime = block.timestamp;
    }

    // ── Fund rewards (called by Treasury) ────────────────────────────

    function fundRewards(uint256 amount) external onlyOwner {
        require(token.transferFrom(msg.sender, address(this), amount), "Transfer failed");
        rewardPool += amount;
        emit RewardFunded(amount);
    }

    // ── Stake ─────────────────────────────────────────────────────────

    function stake(uint256 amount, uint256 tierIndex) external nonReentrant {
        require(amount > 0, "Amount must be > 0");
        require(tierIndex < lockupDurations.length, "Invalid tier");

        _updatePool();

        require(token.transferFrom(msg.sender, address(this), amount), "Transfer failed");

        uint256 lockupEnd  = block.timestamp + lockupDurations[tierIndex];
        uint256 multiplier = lockupMultipliers[tierIndex];

        stakes[msg.sender].push(Stake({
            amount:     amount,
            since:      block.timestamp,
            lockupEnd:  lockupEnd,
            multiplier: multiplier,
            rewardDebt: (amount * multiplier / 10000) * accRewardPerShare / PRECISION
        }));

        totalStaked += amount;

        if (!hasStaked[msg.sender]) {
            hasStaked[msg.sender] = true;
            uniqueStakers++;
        }

        emit Staked(msg.sender, amount, lockupDurations[tierIndex] / 1 days, stakes[msg.sender].length - 1);
    }

    // ── Unstake ───────────────────────────────────────────────────────

    function unstake(uint256 stakeIndex) external nonReentrant {
        require(stakeIndex < stakes[msg.sender].length, "Invalid index");
        Stake storage s = stakes[msg.sender][stakeIndex];
        require(s.amount > 0, "Already unstaked");
        require(block.timestamp >= s.lockupEnd, "Still locked");

        _updatePool();

        uint256 effectiveAmount = s.amount * s.multiplier / 10000;
        uint256 pending = effectiveAmount * accRewardPerShare / PRECISION - s.rewardDebt;

        uint256 amount = s.amount;
        s.amount     = 0;
        s.rewardDebt = 0;
        totalStaked -= amount;

        // Return principal
        require(token.transfer(msg.sender, amount), "Transfer failed");

        // Pay rewards from pool
        if (pending > 0 && rewardPool >= pending) {
            rewardPool -= pending;
            require(token.transfer(msg.sender, pending), "Reward transfer failed");
            totalRewardsClaimed += pending;
            emit RewardClaimed(msg.sender, pending);
        }

        emit Unstaked(msg.sender, amount, pending, stakeIndex);
    }

    // ── Claim rewards without unstaking ──────────────────────────────

    function claimRewards(uint256 stakeIndex) external nonReentrant {
        require(stakeIndex < stakes[msg.sender].length, "Invalid index");
        Stake storage s = stakes[msg.sender][stakeIndex];
        require(s.amount > 0, "Not staked");

        _updatePool();

        uint256 effectiveAmount = s.amount * s.multiplier / 10000;
        uint256 pending = effectiveAmount * accRewardPerShare / PRECISION - s.rewardDebt;
        s.rewardDebt = effectiveAmount * accRewardPerShare / PRECISION;

        if (pending > 0 && rewardPool >= pending) {
            rewardPool -= pending;
            require(token.transfer(msg.sender, pending), "Transfer failed");
            totalRewardsClaimed += pending;
            emit RewardClaimed(msg.sender, pending);
        }
    }

    // ── Pool update (reward distribution) ────────────────────────────

    function _updatePool() internal {
        if (totalStaked == 0) {
            lastRewardTime = block.timestamp;
            return;
        }

        uint256 elapsed  = block.timestamp - lastRewardTime;
        if (elapsed == 0) return;

        // Distribute at most 1/365 of reward pool per day (emergent APY)
        uint256 dailyRate   = rewardPool / 365;
        uint256 toDistribute = dailyRate * elapsed / 1 days;
        if (toDistribute > rewardPool) toDistribute = rewardPool;

        if (toDistribute > 0) {
            accRewardPerShare += toDistribute * PRECISION / totalStaked;
            rewardPool        -= toDistribute;
        }

        lastRewardTime = block.timestamp;
    }

    // ── View helpers ──────────────────────────────────────────────────

    function pendingRewards(address user, uint256 stakeIndex)
        external view returns (uint256)
    {
        if (stakeIndex >= stakes[user].length) return 0;
        Stake memory s = stakes[user][stakeIndex];
        if (s.amount == 0) return 0;

        uint256 _accRPS = accRewardPerShare;
        if (totalStaked > 0) {
            uint256 elapsed       = block.timestamp - lastRewardTime;
            uint256 toDistribute  = (rewardPool / 365) * elapsed / 1 days;
            if (toDistribute > rewardPool) toDistribute = rewardPool;
            _accRPS += toDistribute * PRECISION / totalStaked;
        }

        uint256 effective = s.amount * s.multiplier / 10000;
        return effective * _accRPS / PRECISION - s.rewardDebt;
    }

    function getStakes(address user) external view returns (Stake[] memory) {
        return stakes[user];
    }

    function stakeCount(address user) external view returns (uint256) {
        return stakes[user].length;
    }

    /// @notice Annualised yield based on current pool and total staked
    function currentAPY() external view returns (uint256) {
        if (totalStaked == 0) return 0;
        return rewardPool * 10000 / totalStaked; // bps
    }
}
