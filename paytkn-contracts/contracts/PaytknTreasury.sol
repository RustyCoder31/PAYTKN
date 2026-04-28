// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./PaytknToken.sol";
import "./PaytknStaking.sol";
import "./MerchantStaking.sol";
import "./RewardEngine.sol";

/**
 * @title PaytknTreasury
 * @notice Central hub for all protocol fee flows.
 *
 * Payment flow:
 *   1. Merchant accepts payment → sends 0.5% protocol fee here (in ETH/stablecoin sim)
 *   2. Treasury splits fee: 10% team, rewardAlloc% -> staking pool, merchantAlloc% -> merchant pool
 *   3. Treasury mints cashback to user (cashbackBaseBps% of payment)
 *   4. RL agent calls updateParameters() daily to adjust all levers
 *
 * For demo: ETH is used as the "stablecoin" stand-in.
 *           Real deployment would use USDC on Base.
 */
contract PaytknTreasury is AccessControl, ReentrancyGuard {

    bytes32 public constant AGENT_ROLE     = keccak256("AGENT_ROLE");
    bytes32 public constant OPERATOR_ROLE  = keccak256("OPERATOR_ROLE");

    PaytknToken     public immutable token;
    PaytknStaking   public immutable staking;
    MerchantStaking public immutable merchantStaking;
    RewardEngine    public immutable rewardEngine;

    address public teamWallet;

    // ── Treasury balances ─────────────────────────────────────────────
    uint256 public stableReserve;    // ETH in treasury (wei) — stable stand-in
    uint256 public merchantPool;     // PAYTKN for merchant staking rewards

    // ── Protocol stats ────────────────────────────────────────────────
    uint256 public totalPaymentsProcessed;
    uint256 public totalFeesCollected;    // wei
    uint256 public totalCashbackMinted;
    uint256 public totalBurnedByAgent;

    // ── Price oracle (demo: manually set, production: Chainlink) ──────
    uint256 public paytknPriceUsd;   // scaled 1e8 (e.g. 1e8 = $1.00)
    uint256 public lastPriceUpdate;

    // ── Events ────────────────────────────────────────────────────────
    event PaymentProcessed(
        address indexed user,
        address indexed merchant,
        uint256 paymentAmount,
        uint256 fee,
        uint256 cashback
    );
    event FeeDistributed(
        uint256 toTeam,
        uint256 toRewardPool,
        uint256 toMerchantPool,
        uint256 toTreasury
    );
    event AgentBurn(uint256 amount, uint256 timestamp);
    event PriceUpdated(uint256 newPrice, uint256 timestamp);
    event StableWithdrawn(address indexed to, uint256 amount);

    constructor(
        address _token,
        address _staking,
        address _merchantStaking,
        address _rewardEngine,
        address _teamWallet,
        address admin
    ) {
        token           = PaytknToken(_token);
        staking         = PaytknStaking(_staking);
        merchantStaking = MerchantStaking(_merchantStaking);
        rewardEngine    = RewardEngine(_rewardEngine);
        teamWallet      = _teamWallet;

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(AGENT_ROLE, admin);
        _grantRole(OPERATOR_ROLE, admin);

        paytknPriceUsd = 1e8; // $1.00 at launch
    }

    // ── Receive ETH (stable reserve funding) ─────────────────────────

    receive() external payable {
        stableReserve += msg.value;
    }

    // ── Process payment (called by merchant backend) ──────────────────

    /**
     * @notice Simulate a PAYTKN payment.
     *         In production: user sends PAYTKN (or any token via LI.FI bridge).
     *         For demo: ETH sent here represents payment amount.
     *
     * @param user     Customer wallet
     * @param merchant Merchant wallet
     */
    function processPayment(address user, address merchant)
        external
        payable
        nonReentrant
        onlyRole(OPERATOR_ROLE)
    {
        require(msg.value > 0, "No payment");

        uint256 paymentAmount = msg.value;
        uint256 fee           = paymentAmount * 50 / 10000;  // 0.5% protocol fee
        uint256 toMerchant    = paymentAmount - fee;

        // Send payment to merchant
        (bool sent,) = merchant.call{value: toMerchant}("");
        require(sent, "Merchant payment failed");

        // Distribute fee
        _distributeFee(fee);

        // Mint cashback to user
        uint256 cashbackBps = token.cashbackBaseBps();
        uint256 cashbackEth = paymentAmount * cashbackBps / 10000;
        // Convert ETH value to PAYTKN at current price
        uint256 cashbackPAYTKN = cashbackEth * 1e8 / paytknPriceUsd;
        if (cashbackPAYTKN > 0) {
            token.payCashback(user, cashbackPAYTKN);
            totalCashbackMinted += cashbackPAYTKN;
        }

        totalPaymentsProcessed++;
        totalFeesCollected += fee;

        emit PaymentProcessed(user, merchant, paymentAmount, fee, cashbackPAYTKN);
    }

    function _distributeFee(uint256 fee) internal {
        uint256 toTeam        = fee * 1000 / 10000;  // 10%
        uint256 rewardAllocBps = token.rewardAllocBps();
        uint256 merchantAllocBps = token.merchantAllocBps();

        uint256 toRewardPool  = fee * rewardAllocBps  / 10000;
        uint256 toMerchant_   = fee * merchantAllocBps / 10000;
        uint256 toTreasury    = fee - toTeam - toRewardPool - toMerchant_;

        // Team fee
        (bool teamSent,) = teamWallet.call{value: toTeam}("");
        require(teamSent, "Team payment failed");

        // Treasury reserve
        stableReserve += toTreasury;

        // Reward pool: convert ETH → PAYTKN and fund staking contract
        if (toRewardPool > 0) {
            uint256 rewardPAYTKN = toRewardPool * 1e8 / paytknPriceUsd;
            if (rewardPAYTKN > 0 && token.balanceOf(address(this)) >= rewardPAYTKN) {
                token.approve(address(staking), rewardPAYTKN);
                staking.fundRewards(rewardPAYTKN);
            }
        }

        // Merchant pool (PAYTKN)
        if (toMerchant_ > 0) {
            uint256 merchantPAYTKN = toMerchant_ * 1e8 / paytknPriceUsd;
            merchantPool += merchantPAYTKN;
        }

        emit FeeDistributed(toTeam, toRewardPool, toMerchant_, toTreasury);
    }

    // ── RL Agent daily burn ───────────────────────────────────────────

    /**
     * @notice Agent triggers daily burn of treasury PAYTKN.
     *         Amount = treasury_paytkn_balance * burnRateBps / 10000
     */
    function executeDailyBurn() external onlyRole(AGENT_ROLE) {
        uint256 balance = token.balanceOf(address(this));
        uint256 burnBps = token.burnRateBps();
        uint256 amount  = balance * burnBps / 10000;
        if (amount > 0) {
            token.burn(amount);
            totalBurnedByAgent += amount;
            emit AgentBurn(amount, block.timestamp);
        }
    }

    // ── RL Agent adaptive mint ────────────────────────────────────────

    /**
     * @notice Agent triggers adaptive mint based on tx volume and price stability.
     *         For demo: mint amount passed directly by agent.
     */
    function executeMint(uint256 amount) external onlyRole(AGENT_ROLE) {
        require(amount <= 100_000 * 1e18, "Mint too large for single tx");
        uint256 treasuryRatio = token.treasuryRatioBps();
        uint256 toTreasury    = amount * treasuryRatio / 10000;
        uint256 toReward      = amount - toTreasury;

        // Mint to treasury
        if (toTreasury > 0) token.mint(address(this), toTreasury);

        // Mint to staking reward pool
        if (toReward > 0) {
            token.mint(address(this), toReward);
            token.approve(address(staking), toReward);
            staking.fundRewards(toReward);
        }
    }

    // ── Price oracle update (agent / operator) ────────────────────────

    function updatePrice(uint256 newPrice) external onlyRole(OPERATOR_ROLE) {
        require(newPrice > 0, "Price must be > 0");
        paytknPriceUsd  = newPrice;
        lastPriceUpdate = block.timestamp;
        emit PriceUpdated(newPrice, block.timestamp);
    }

    // ── Admin: withdraw stable reserve ────────────────────────────────

    function withdrawStable(address to, uint256 amount)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
        nonReentrant
    {
        require(amount <= stableReserve, "Insufficient reserve");
        stableReserve -= amount;
        (bool sent,) = to.call{value: amount}("");
        require(sent, "Withdraw failed");
        emit StableWithdrawn(to, amount);
    }

    // ── View: full protocol state (for RL agent observation) ──────────

    function getProtocolState() external view returns (
        uint256 _stableReserve,
        uint256 _paytknBalance,
        uint256 _totalStaked,
        uint256 _rewardPool,
        uint256 _currentAPY,
        uint256 _totalSupply,
        uint256 _paytknPrice,
        uint256 _totalPayments,
        uint256 _totalFees,
        uint256 _merchantPool
    ) {
        return (
            stableReserve,
            token.balanceOf(address(this)),
            staking.totalStaked(),
            staking.rewardPool(),
            staking.currentAPY(),
            token.totalSupply(),
            paytknPriceUsd,
            totalPaymentsProcessed,
            totalFeesCollected,
            merchantPool
        );
    }
}
