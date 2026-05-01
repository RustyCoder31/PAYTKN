/**
 * Deploy PaytknGateway — public ETH-to-PAYTKN payment contract.
 *
 * Run:
 *   npx hardhat run scripts/deployGateway.js --network baseSepolia
 *
 * What this does:
 *   1. Deploys PaytknGateway with rate = 3000 (1 ETH → 3000 PAYTKN)
 *   2. Funds the gateway with 500,000 PAYTKN from the deployer balance
 *   3. Saves gateway address to deployed-addresses.json
 *   4. Logs the address — copy it into frontend/src/lib/web3.ts GATEWAY_ADDRESS
 */
const { ethers, network } = require("hardhat");
const fs = require("fs");

const ADDRESSES = JSON.parse(fs.readFileSync("deployed-addresses.json", "utf8"));

// 1 ETH = 3000 PAYTKN  (at $1/PAYTKN and $3000/ETH)
// Testnet demo: user sends 0.001 ETH → merchant gets ~2.985 PAYTKN
const ETH_TO_PAYTKN_RATE = 3000n;

// How much PAYTKN to pre-load into the gateway
const GATEWAY_FUND_AMOUNT = ethers.parseEther("500000"); // 500,000 PAYTKN

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("\n=================================================");
  console.log("  PAYTKN Gateway — Deploying to", network.name);
  console.log("  Deployer:", deployer.address);
  const ethBal = await ethers.provider.getBalance(deployer.address);
  console.log("  ETH Balance:", ethers.formatEther(ethBal));
  console.log("=================================================\n");

  // ── Load existing token ──────────────────────────────────────────────────
  const token = await ethers.getContractAt("PaytknToken", ADDRESSES.token);
  const deployerPAYTKN = await token.balanceOf(deployer.address);
  console.log("  Deployer PAYTKN balance:", ethers.formatEther(deployerPAYTKN));

  if (deployerPAYTKN < GATEWAY_FUND_AMOUNT) {
    console.error(`\n❌ Deployer needs at least 500,000 PAYTKN — has ${ethers.formatEther(deployerPAYTKN)}`);
    console.error("   Tip: token genesis minted 12M to deployer; 2M went to treasury → you should have ~10M.");
    process.exit(1);
  }

  // ── Deploy Gateway ───────────────────────────────────────────────────────
  console.log("\nDeploying PaytknGateway...");
  const Gateway = await ethers.getContractFactory("PaytknGateway");
  const gateway = await Gateway.deploy(
    ADDRESSES.token,        // PAYTKN token
    ETH_TO_PAYTKN_RATE,     // 3000 PAYTKN per 1 ETH
    deployer.address        // owner
  );
  await gateway.waitForDeployment();
  const gatewayAddr = await gateway.getAddress();
  console.log("  PaytknGateway →", gatewayAddr);

  // ── Fund with PAYTKN ─────────────────────────────────────────────────────
  console.log("\nFunding gateway with 500,000 PAYTKN...");
  const tx = await token.transfer(gatewayAddr, GATEWAY_FUND_AMOUNT);
  await tx.wait();
  const gwBal = await token.balanceOf(gatewayAddr);
  console.log("  Gateway PAYTKN balance:", ethers.formatEther(gwBal));

  // ── Verify ───────────────────────────────────────────────────────────────
  const preview = await gateway.previewPayment(ethers.parseEther("0.001"));
  console.log("\n  ✅ Preview: 0.001 ETH payment →");
  console.log("     Fee:     ", ethers.formatEther(preview.feeEth), "ETH");
  console.log("     Net:     ", ethers.formatEther(preview.netEth), "ETH");
  console.log("     Merchant:", ethers.formatEther(preview.paytknToMerchant), "PAYTKN");

  // ── Save ─────────────────────────────────────────────────────────────────
  ADDRESSES.gateway    = gatewayAddr;
  ADDRESSES.gatewayRate = ETH_TO_PAYTKN_RATE.toString();
  ADDRESSES.gatewayFunded = ethers.formatEther(GATEWAY_FUND_AMOUNT);
  fs.writeFileSync("deployed-addresses.json", JSON.stringify(ADDRESSES, null, 2));
  console.log("\n  Addresses saved → deployed-addresses.json");

  console.log("\n=================================================");
  console.log("  GATEWAY DEPLOYED ✅");
  console.log("  Address:", gatewayAddr);
  console.log("  Rate:   ", ETH_TO_PAYTKN_RATE.toString(), "PAYTKN / 1 ETH");
  console.log("  Funded: 500,000 PAYTKN");
  console.log("=================================================");
  console.log("\n⚠️  NOW UPDATE frontend/src/lib/web3.ts:");
  console.log(`   GATEWAY_ADDRESS = "${gatewayAddr}"`);
  console.log("=================================================\n");
}

main().catch((e) => { console.error(e); process.exit(1); });
