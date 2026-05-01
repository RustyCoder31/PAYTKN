// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title PaytknGateway
 * @notice Public-facing crypto payment gateway.
 *
 *   User sends ETH from their MetaMask  →  Merchant receives PAYTKN.
 *
 *   No role restriction — callable by ANY wallet.
 *   Pre-funded with PAYTKN by the owner; ETH is collected as protocol revenue.
 *
 * Rate:
 *   paytknAmount = netEth * ethToPaytknRate
 *   e.g. rate = 3000  →  1 ETH = 3000 PAYTKN  ($1 PAYTKN / $3000 ETH)
 *        sending 0.001 ETH  →  ~2.985 PAYTKN to merchant (after 0.5% fee)
 *
 * Deployment:
 *   1. Deploy with token address, rate, owner
 *   2. Transfer PAYTKN to this contract address to fund it
 *   3. Any user can now call pay(merchantAddr) with ETH value
 */
contract PaytknGateway is Ownable, ReentrancyGuard {

    IERC20  public immutable token;
    uint256 public ethToPaytknRate; // PAYTKN per 1 ETH (e.g. 3000)
    uint256 public constant FEE_BPS = 50; // 0.5% protocol fee

    // ── Protocol stats ────────────────────────────────────────────────────────
    uint256 public totalEthReceived;
    uint256 public totalPaytknSent;
    uint256 public totalPayments;

    // ── Events ────────────────────────────────────────────────────────────────
    event Payment(
        address indexed user,
        address indexed merchant,
        uint256 ethAmount,       // total ETH sent by user (wei)
        uint256 feeEth,          // 0.5% kept in gateway (wei)
        uint256 paytknToMerchant,// PAYTKN transferred to merchant (1e18)
        uint256 timestamp
    );
    event RateUpdated(uint256 oldRate, uint256 newRate);
    event GatewayFunded(address indexed by, uint256 paytknAmount);

    constructor(address _token, uint256 _rate, address _owner) Ownable(_owner) {
        require(_token  != address(0), "Zero token address");
        require(_rate   >  0,          "Rate must be > 0");
        token              = IERC20(_token);
        ethToPaytknRate    = _rate;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Core: public pay function — anyone can call, no role needed
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Pay a merchant.  User sends ETH, merchant receives PAYTKN.
     * @param merchant  The merchant's wallet address.
     *
     * math (all in wei / 1e18 units):
     *   fee            = msg.value * 50 / 10000          (0.5%)
     *   net            = msg.value - fee
     *   paytknAmount   = net * ethToPaytknRate
     *   (since 1 ETH = 1e18 wei and 1 PAYTKN = 1e18 units,
     *    multiplying wei * rate gives the correct PAYTKN token units)
     */
    function pay(address merchant) external payable nonReentrant {
        require(msg.value  > 0,             "No ETH sent");
        require(merchant   != address(0),   "Invalid merchant");
        require(merchant   != msg.sender,   "Cannot pay yourself");

        uint256 fee          = msg.value * FEE_BPS / 10000;
        uint256 net          = msg.value - fee;
        uint256 paytknAmount = net * ethToPaytknRate;  // wei * (PAYTKN/ETH) = PAYTKN wei

        require(
            token.balanceOf(address(this)) >= paytknAmount,
            "Gateway underfunded: owner must top up PAYTKN"
        );

        bool ok = token.transfer(merchant, paytknAmount);
        require(ok, "PAYTKN transfer failed");

        totalEthReceived  += msg.value;
        totalPaytknSent   += paytknAmount;
        totalPayments     += 1;

        emit Payment(msg.sender, merchant, msg.value, fee, paytknAmount, block.timestamp);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // View helpers
    // ─────────────────────────────────────────────────────────────────────────

    function paytknBalance() external view returns (uint256) {
        return token.balanceOf(address(this));
    }

    function ethBalance() external view returns (uint256) {
        return address(this).balance;
    }

    /**
     * @notice Preview how much PAYTKN a given ETH amount will send to merchant.
     * @param ethWei  Amount in wei the user intends to send.
     */
    function previewPayment(uint256 ethWei) external view returns (
        uint256 feeEth,
        uint256 netEth,
        uint256 paytknToMerchant
    ) {
        feeEth           = ethWei * FEE_BPS / 10000;
        netEth           = ethWei - feeEth;
        paytknToMerchant = netEth * ethToPaytknRate;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Owner admin
    // ─────────────────────────────────────────────────────────────────────────

    function setRate(uint256 newRate) external onlyOwner {
        require(newRate > 0, "Rate must be > 0");
        emit RateUpdated(ethToPaytknRate, newRate);
        ethToPaytknRate = newRate;
    }

    function withdrawETH(address payable to, uint256 amount) external onlyOwner {
        require(amount <= address(this).balance, "Insufficient ETH in gateway");
        (bool ok,) = to.call{value: amount}("");
        require(ok, "ETH withdraw failed");
    }

    function withdrawPAYTKN(address to, uint256 amount) external onlyOwner {
        require(token.transfer(to, amount), "PAYTKN withdraw failed");
    }

    receive() external payable {
        totalEthReceived += msg.value;
    }
}
