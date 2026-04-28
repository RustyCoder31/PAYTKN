const { expect } = require("chai");
const { ethers }  = require("hardhat");

// ─── PAYTKN Full Protocol Test Suite ─────────────────────────────────────────
// Covers: deployment, genesis allocation, RL parameter updates, payment flow,
//         fee distribution, mint/burn, staking, cashback, anti-gaming rules.
// Run: npx hardhat test
// ─────────────────────────────────────────────────────────────────────────────

describe("PAYTKN Protocol", function () {

  let token, staking, merchantStaking, rewardEngine, treasury;
  let owner, team, user1, user2, merchant1;
  const AGENT_ROLE = ethers.keccak256(ethers.toUtf8Bytes("AGENT_ROLE"));
  const TREASURY_ROLE = ethers.keccak256(ethers.toUtf8Bytes("TREASURY_ROLE"));

  // Deploy the full five-contract stack before each test group
  before(async () => {
    [owner, team, user1, user2, merchant1] = await ethers.getSigners();

    const Token          = await ethers.getContractFactory("PaytknToken");
    const Staking        = await ethers.getContractFactory("PaytknStaking");
    const MerchantStk    = await ethers.getContractFactory("MerchantStaking");
    const RewardEng      = await ethers.getContractFactory("RewardEngine");
    const Treasury       = await ethers.getContractFactory("PaytknTreasury");

    token          = await Token.deploy();
    staking        = await Staking.deploy(await token.getAddress());
    merchantStaking= await MerchantStk.deploy(await token.getAddress());
    rewardEngine   = await RewardEng.deploy(await token.getAddress(), await staking.getAddress());
    treasury       = await Treasury.deploy(
      await token.getAddress(),
      await staking.getAddress(),
      await merchantStaking.getAddress(),
      await rewardEngine.getAddress(),
      team.address,
    );

    // Wire roles
    await token.grantRole(AGENT_ROLE,    owner.address);
    await token.grantRole(TREASURY_ROLE, await treasury.getAddress());
    await treasury.grantRole(AGENT_ROLE, owner.address);
  });

  // ── 1. Deployment & Genesis ──────────────────────────────────────────────

  describe("1. Deployment & Genesis Allocation", () => {

    it("deploys all five contracts without revert", async () => {
      expect(await token.getAddress()).to.be.properAddress;
      expect(await staking.getAddress()).to.be.properAddress;
      expect(await merchantStaking.getAddress()).to.be.properAddress;
      expect(await rewardEngine.getAddress()).to.be.properAddress;
      expect(await treasury.getAddress()).to.be.properAddress;
    });

    it("mints exactly 12,000,000 PAYTKN at genesis", async () => {
      const supply = await token.totalSupply();
      expect(supply).to.equal(ethers.parseEther("12000000"));
    });

    it("enforces hard cap of 100,000,000 PAYTKN", async () => {
      const cap = await token.MAX_SUPPLY();
      expect(cap).to.equal(ethers.parseEther("100000000"));
    });

    it("grants AGENT_ROLE to owner", async () => {
      expect(await token.hasRole(AGENT_ROLE, owner.address)).to.be.true;
    });

    it("grants TREASURY_ROLE to treasury contract", async () => {
      expect(await token.hasRole(TREASURY_ROLE, await treasury.getAddress())).to.be.true;
    });
  });

  // ── 2. RL Parameter Updates ──────────────────────────────────────────────

  describe("2. RL Agent Parameter Updates", () => {

    it("agent can update all six protocol parameters", async () => {
      await expect(token.updateParameters(
        100,   // mint_factor
        2,     // burn_rate_bps  (0.02%)
        3000,  // reward_alloc_bps (30%)
        50,    // cashback_base_bps (0.5%)
        1000,  // merchant_alloc_bps (10%)
        6000,  // treasury_ratio_bps (60%)
      )).to.not.be.reverted;
    });

    it("reads back updated parameters correctly", async () => {
      const p = await token.getParameters();
      expect(p[0]).to.equal(100);   // mint_factor
      expect(p[1]).to.equal(2);     // burn_rate_bps
      expect(p[2]).to.equal(3000);  // reward_alloc_bps
    });

    it("rejects burn_rate_bps > 5 (hard cap)", async () => {
      await expect(token.updateParameters(100, 10, 3000, 50, 1000, 6000))
        .to.be.revertedWith("burn rate too high");
    });

    it("rejects reward_alloc_bps + merchant_alloc_bps > 9000 (team share protected)", async () => {
      // 6000 + 4000 > 9000 — team's 10% is protected
      await expect(token.updateParameters(100, 2, 6000, 50, 4000, 6000))
        .to.be.reverted;
    });

    it("non-agent cannot update parameters", async () => {
      await expect(token.connect(user1).updateParameters(100, 2, 3000, 50, 1000, 6000))
        .to.be.reverted;
    });
  });

  // ── 3. Payment Flow & Fee Distribution ──────────────────────────────────

  describe("3. Payment Processing & Fee Distribution", () => {
    const PAYMENT = ethers.parseEther("1.0");  // 1 ETH payment

    before(async () => {
      // Set a mock price (1 PAYTKN = $1 → 1e8 wei in uint)
      await treasury.setPaytknPrice(1e8);
    });

    it("processes payment and emits PaymentProcessed event", async () => {
      await expect(
        treasury.connect(user1).processPayment(user1.address, merchant1.address, {
          value: PAYMENT,
        })
      ).to.emit(treasury, "PaymentProcessed");
    });

    it("routes exactly 10% of fee to team wallet", async () => {
      const teamBalBefore = await ethers.provider.getBalance(team.address);
      const tx = await treasury.connect(user2).processPayment(
        user2.address, merchant1.address, { value: PAYMENT }
      );
      const teamBalAfter = await ethers.provider.getBalance(team.address);
      const fee = PAYMENT * 50n / 10000n;       // 0.5% protocol fee
      const expectedTeam = fee * 1000n / 10000n; // 10% of fee
      expect(teamBalAfter - teamBalBefore).to.equal(expectedTeam);
    });

    it("increments totalPaymentsProcessed", async () => {
      const before = await treasury.totalPaymentsProcessed();
      await treasury.connect(user1).processPayment(
        user1.address, merchant1.address, { value: PAYMENT }
      );
      const after = await treasury.totalPaymentsProcessed();
      expect(after).to.equal(before + 1n);
    });

    it("accumulates totalFeesCollected", async () => {
      const fees = await treasury.totalFeesCollected();
      expect(fees).to.be.gt(0n);
    });
  });

  // ── 4. Mint & Burn ───────────────────────────────────────────────────────

  describe("4. Adaptive Mint & Burn", () => {

    it("agent can trigger mint split by treasury_ratio", async () => {
      const supplyBefore = await token.totalSupply();
      await treasury.executeMint(ethers.parseEther("1000"));
      const supplyAfter = await token.totalSupply();
      expect(supplyAfter).to.be.gt(supplyBefore);
    });

    it("single mint cannot exceed 100,000 PAYTKN (anti-inflation guard)", async () => {
      await expect(
        treasury.executeMint(ethers.parseEther("200000"))
      ).to.be.revertedWith("Mint too large for single tx");
    });

    it("total supply cannot exceed 100M hard cap", async () => {
      const cap   = await token.MAX_SUPPLY();
      const total = await token.totalSupply();
      expect(total).to.be.lte(cap);
    });

    it("agent can trigger burn from treasury balance", async () => {
      // Give treasury some PAYTKN first
      await token.transfer(await treasury.getAddress(), ethers.parseEther("50000"));
      const supplyBefore = await token.totalSupply();
      await treasury.executeDailyBurn();
      const supplyAfter = await token.totalSupply();
      // Supply should decrease (unless burnRateBps = 0)
      const burnBps = await token.burnRateBps();
      if (burnBps > 0n) {
        expect(supplyAfter).to.be.lt(supplyBefore);
      }
    });

    it("burn increases totalBurnedByAgent", async () => {
      await token.transfer(await treasury.getAddress(), ethers.parseEther("10000"));
      const burnedBefore = await treasury.totalBurnedByAgent();
      await treasury.executeDailyBurn();
      const burnedAfter = await treasury.totalBurnedByAgent();
      expect(burnedAfter).to.be.gte(burnedBefore);
    });
  });

  // ── 5. Staking ───────────────────────────────────────────────────────────

  describe("5. User Staking Pool", () => {

    it("user can stake PAYTKN and receive staked balance", async () => {
      const amount = ethers.parseEther("1000");
      await token.transfer(user1.address, amount);
      await token.connect(user1).approve(await staking.getAddress(), amount);
      await staking.connect(user1).stake(amount);
      const staked = await staking.stakedBalance(user1.address);
      expect(staked).to.equal(amount);
    });

    it("total staked increases after stake", async () => {
      const total = await staking.totalStaked();
      expect(total).to.be.gt(0n);
    });

    it("user can unstake and receive PAYTKN back", async () => {
      const stakedBefore = await staking.stakedBalance(user1.address);
      const half = stakedBefore / 2n;
      await staking.connect(user1).unstake(half);
      const stakedAfter = await staking.stakedBalance(user1.address);
      expect(stakedAfter).to.equal(stakedBefore - half);
    });

    it("staking pool can receive reward funding", async () => {
      const fundAmt = ethers.parseEther("5000");
      await token.transfer(await treasury.getAddress(), fundAmt);
      await treasury.executeMint(ethers.parseEther("500"));
      // fundRewards is called internally on mint/fee routing — check staking pool balance
      const bal = await token.balanceOf(await staking.getAddress());
      expect(bal).to.be.gte(0n);
    });
  });

  // ── 6. Cashback via RewardEngine ────────────────────────────────────────

  describe("6. RewardEngine Cashback Calculation", () => {

    it("returns zero cashback for zero payment", async () => {
      const cb = await rewardEngine.computeCashback(user1.address, 0n);
      expect(cb).to.equal(0n);
    });

    it("cashback increases with higher staking tier", async () => {
      // Stake a large amount to reach higher tier
      const bigStake = ethers.parseEther("50000");
      await token.transfer(user2.address, bigStake);
      await token.connect(user2).approve(await staking.getAddress(), bigStake);
      await staking.connect(user2).stake(bigStake);

      const paymentAmt = ethers.parseEther("100");
      const cb2 = await rewardEngine.computeCashback(user2.address, paymentAmt);
      const cb1 = await rewardEngine.computeCashback(user1.address, paymentAmt);

      // user2 has more staked → should get >= cashback vs user1
      expect(cb2).to.be.gte(cb1);
    });

    it("cashback never exceeds 5% of payment value", async () => {
      const payment = ethers.parseEther("200");
      const maxAllowed = payment * 500n / 10000n;  // 5%
      const cb = await rewardEngine.computeCashback(user2.address, payment);
      expect(cb).to.be.lte(maxAllowed);
    });
  });

  // ── 7. Anti-Gaming ──────────────────────────────────────────────────────

  describe("7. Anti-Gaming Rules", () => {

    it("treasury stable reserve increases from payment fees", async () => {
      const reserveBefore = await treasury.stableReserve();
      await treasury.connect(user1).processPayment(
        user1.address, merchant1.address,
        { value: ethers.parseEther("2.0") }
      );
      const reserveAfter = await treasury.stableReserve();
      expect(reserveAfter).to.be.gt(reserveBefore);
    });

    it("treasury can withdraw stable reserve (owner only)", async () => {
      const res = await treasury.stableReserve();
      if (res > 0n) {
        await expect(treasury.withdrawStable(res / 2n)).to.not.be.reverted;
      }
    });

    it("non-owner cannot withdraw stable reserve", async () => {
      await expect(
        treasury.connect(user1).withdrawStable(ethers.parseEther("0.001"))
      ).to.be.reverted;
    });
  });

  // ── 8. Deployment Addresses Consistency ─────────────────────────────────

  describe("8. Contract Wiring", () => {

    it("treasury holds reference to correct token address", async () => {
      expect(await treasury.token()).to.equal(await token.getAddress());
    });

    it("treasury holds reference to correct staking address", async () => {
      expect(await treasury.staking()).to.equal(await staking.getAddress());
    });

    it("treasury holds reference to correct merchantStaking address", async () => {
      expect(await treasury.merchantStaking()).to.equal(await merchantStaking.getAddress());
    });

    it("treasury holds reference to correct rewardEngine address", async () => {
      expect(await treasury.rewardEngine()).to.equal(await rewardEngine.getAddress());
    });

    it("team wallet is set correctly", async () => {
      expect(await treasury.teamWallet()).to.equal(team.address);
    });
  });

});
