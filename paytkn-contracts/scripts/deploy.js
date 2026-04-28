const { ethers, network } = require("hardhat");
const fs = require("fs");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("\n=================================================");
  console.log("  PAYTKN — Deploying to", network.name);
  console.log("  Deployer:", deployer.address);
  const bal = await ethers.provider.getBalance(deployer.address);
  console.log("  Balance: ", ethers.formatEther(bal), "ETH");
  console.log("=================================================\n");

  // 1. Deploy Token
  console.log("1/5  Deploying PaytknToken...");
  const Token = await ethers.getContractFactory("PaytknToken");
  const token = await Token.deploy(deployer.address);
  await token.waitForDeployment();
  const tokenAddr = await token.getAddress();
  console.log("     PaytknToken ->", tokenAddr);

  // 2. Deploy User Staking
  console.log("2/5  Deploying PaytknStaking (user pool)...");
  const Staking = await ethers.getContractFactory("PaytknStaking");
  const staking = await Staking.deploy(tokenAddr, deployer.address);
  await staking.waitForDeployment();
  const stakingAddr = await staking.getAddress();
  console.log("     PaytknStaking ->", stakingAddr);

  // 3. Deploy Merchant Staking
  console.log("3/5  Deploying MerchantStaking (merchant pool)...");
  const MerchantStaking = await ethers.getContractFactory("MerchantStaking");
  const merchantStaking = await MerchantStaking.deploy(tokenAddr, deployer.address);
  await merchantStaking.waitForDeployment();
  const merchantStakingAddr = await merchantStaking.getAddress();
  console.log("     MerchantStaking ->", merchantStakingAddr);

  // 4. Deploy Reward Engine
  console.log("4/5  Deploying RewardEngine...");
  const RewardEngine = await ethers.getContractFactory("RewardEngine");
  const rewardEngine = await RewardEngine.deploy(
    tokenAddr, stakingAddr, merchantStakingAddr, deployer.address
  );
  await rewardEngine.waitForDeployment();
  const rewardEngineAddr = await rewardEngine.getAddress();
  console.log("     RewardEngine ->", rewardEngineAddr);

  // 5. Deploy Treasury
  console.log("5/5  Deploying PaytknTreasury...");
  const Treasury = await ethers.getContractFactory("PaytknTreasury");
  const treasury = await Treasury.deploy(
    tokenAddr, stakingAddr, merchantStakingAddr,
    rewardEngineAddr, deployer.address, deployer.address
  );
  await treasury.waitForDeployment();
  const treasuryAddr = await treasury.getAddress();
  console.log("     PaytknTreasury ->", treasuryAddr);

  // 6. Wire up roles
  console.log("\nWiring roles...");
  const MINTER = await token.MINTER_ROLE();
  const BURNER = await token.BURNER_ROLE();
  const AGENT  = await token.AGENT_ROLE();

  await (await token.grantRole(MINTER, treasuryAddr)).wait();
  await (await token.grantRole(BURNER, treasuryAddr)).wait();
  await (await token.grantRole(AGENT,  treasuryAddr)).wait();

  // Treasury owns staking contracts so it can fund them
  await (await staking.transferOwnership(treasuryAddr)).wait();
  await (await merchantStaking.transferOwnership(treasuryAddr)).wait();
  await (await rewardEngine.transferOwnership(treasuryAddr)).wait();

  console.log("  Roles and ownership wired.");

  // 7. Seed treasury with 2M PAYTKN
  console.log("\nSeeding treasury with 2M PAYTKN...");
  await (await token.transfer(treasuryAddr, ethers.parseEther("2000000"))).wait();

  console.log("\n=================================================");
  console.log("  DEPLOYMENT COMPLETE");
  console.log("=================================================");
  console.log("  TOKEN:           ", tokenAddr);
  console.log("  USER STAKING:    ", stakingAddr);
  console.log("  MERCHANT STAKING:", merchantStakingAddr);
  console.log("  REWARD ENGINE:   ", rewardEngineAddr);
  console.log("  TREASURY:        ", treasuryAddr);
  console.log("=================================================\n");

  const addresses = {
    network:         network.name,
    chainId:         network.config.chainId,
    token:           tokenAddr,
    staking:         stakingAddr,
    merchantStaking: merchantStakingAddr,
    rewardEngine:    rewardEngineAddr,
    treasury:        treasuryAddr,
    deployer:        deployer.address,
    deployedAt:      new Date().toISOString(),
  };
  fs.writeFileSync("deployed-addresses.json", JSON.stringify(addresses, null, 2));
  console.log("Addresses saved -> deployed-addresses.json");
}

main().catch((e) => { console.error(e); process.exit(1); });
