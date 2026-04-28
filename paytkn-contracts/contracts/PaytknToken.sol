// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title PaytknToken
 * @notice PAYTKN — Universal crypto payment utility token.
 *         Minting and burning are controlled by the RL Agent (via Treasury).
 *         Cashback is paid directly from the reward pool on each payment.
 *
 * Roles:
 *   DEFAULT_ADMIN_ROLE — deployer (team multisig in production)
 *   MINTER_ROLE        — Treasury contract (RL agent triggers via treasury)
 *   BURNER_ROLE        — Treasury contract
 *   AGENT_ROLE         — RL agent backend wallet (parameter updates)
 */
contract PaytknToken is ERC20, AccessControl, ReentrancyGuard {

    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");
    bytes32 public constant AGENT_ROLE  = keccak256("AGENT_ROLE");

    uint256 public constant MAX_SUPPLY = 100_000_000 * 1e18; // 100M hard cap

    // ── RL-controlled economic parameters (set by agent) ─────────────
    uint256 public mintFactor;        // basis points: 100 = 1x adaptive mint
    uint256 public burnRateBps;       // basis points per day: 5 = 0.05%/day
    uint256 public rewardAllocBps;    // basis points of fees -> reward pool
    uint256 public cashbackBaseBps;   // basis points: 10 = 0.1% cashback
    uint256 public merchantAllocBps;  // basis points of fees -> merchant pool
    uint256 public treasuryRatioBps;  // basis points: mint split treasury vs reward

    // ── Stats ─────────────────────────────────────────────────────────
    uint256 public totalMinted;
    uint256 public totalBurned;
    uint256 public totalCashbackPaid;
    uint256 public lastAgentUpdate;

    // ── Events ────────────────────────────────────────────────────────
    event ParametersUpdated(
        uint256 mintFactor,
        uint256 burnRateBps,
        uint256 rewardAllocBps,
        uint256 cashbackBaseBps,
        uint256 merchantAllocBps,
        uint256 treasuryRatioBps,
        uint256 timestamp
    );
    event CashbackPaid(address indexed user, uint256 amount);
    event AgentMint(address indexed to, uint256 amount);
    event AgentBurn(uint256 amount);

    constructor(address admin) ERC20("PAYTKN", "PAYTKN") {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(MINTER_ROLE, admin);
        _grantRole(BURNER_ROLE, admin);
        _grantRole(AGENT_ROLE, admin);

        // Genesis: 12M tokens (10M to liquidity pool + 2M treasury)
        uint256 genesis = 12_000_000 * 1e18;
        _mint(admin, genesis);
        totalMinted = genesis;

        // Default parameters (midpoint of action bounds)
        mintFactor       = 100;   // 1.0x adaptive mint
        burnRateBps      = 2;     // 0.02%/day
        rewardAllocBps   = 3000;  // 30% of fees to reward pool
        cashbackBaseBps  = 50;    // 0.5% base cashback
        merchantAllocBps = 1000;  // 10% of fees to merchant pool
        treasuryRatioBps = 6000;  // 60% of mint to treasury
    }

    // ── RL Agent parameter update ─────────────────────────────────────

    /**
     * @notice Called by the RL agent backend to push new economic parameters.
     *         All values in basis points (1 bps = 0.01%).
     */
    function updateParameters(
        uint256 _mintFactor,
        uint256 _burnRateBps,
        uint256 _rewardAllocBps,
        uint256 _cashbackBaseBps,
        uint256 _merchantAllocBps,
        uint256 _treasuryRatioBps
    ) external onlyRole(AGENT_ROLE) {
        require(_mintFactor       <= 200,   "mintFactor > 2x");
        require(_burnRateBps      <= 5,     "burn > 0.05%/day");
        require(_rewardAllocBps   <= 6000,  "rewardAlloc > 60%");
        require(_cashbackBaseBps  <= 100,   "cashback > 1%");
        require(_merchantAllocBps <= 2500,  "merchantAlloc > 25%");
        require(_treasuryRatioBps <= 9000,  "treasuryRatio > 90%");
        require(_rewardAllocBps + _merchantAllocBps <= 8000, "alloc > 80%");

        mintFactor       = _mintFactor;
        burnRateBps      = _burnRateBps;
        rewardAllocBps   = _rewardAllocBps;
        cashbackBaseBps  = _cashbackBaseBps;
        merchantAllocBps = _merchantAllocBps;
        treasuryRatioBps = _treasuryRatioBps;
        lastAgentUpdate  = block.timestamp;

        emit ParametersUpdated(
            _mintFactor, _burnRateBps, _rewardAllocBps,
            _cashbackBaseBps, _merchantAllocBps, _treasuryRatioBps,
            block.timestamp
        );
    }

    // ── Mint / Burn (Treasury only) ───────────────────────────────────

    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        require(totalSupply() + amount <= MAX_SUPPLY, "Exceeds max supply");
        _mint(to, amount);
        totalMinted += amount;
        emit AgentMint(to, amount);
    }

    function burn(uint256 amount) external onlyRole(BURNER_ROLE) {
        _burn(msg.sender, amount);
        totalBurned += amount;
        emit AgentBurn(amount);
    }

    // ── Cashback (called by Treasury on payment) ──────────────────────

    function payCashback(address user, uint256 amount)
        external
        onlyRole(MINTER_ROLE)
        nonReentrant
    {
        require(totalSupply() + amount <= MAX_SUPPLY, "Exceeds max supply");
        _mint(user, amount);
        totalCashbackPaid += amount;
        emit CashbackPaid(user, amount);
    }

    // ── View helpers ──────────────────────────────────────────────────

    function getParameters() external view returns (
        uint256 _mintFactor,
        uint256 _burnRateBps,
        uint256 _rewardAllocBps,
        uint256 _cashbackBaseBps,
        uint256 _merchantAllocBps,
        uint256 _treasuryRatioBps,
        uint256 _lastUpdate
    ) {
        return (
            mintFactor, burnRateBps, rewardAllocBps,
            cashbackBaseBps, merchantAllocBps, treasuryRatioBps,
            lastAgentUpdate
        );
    }

    function circulatingSupply() external view returns (uint256) {
        return totalSupply();
    }
}
