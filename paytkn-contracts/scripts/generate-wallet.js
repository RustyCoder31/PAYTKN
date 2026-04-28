const { ethers } = require("hardhat");

async function main() {
  const wallet = ethers.Wallet.createRandom();

  console.log("\n=================================================");
  console.log("  PAYTKN — New Deployment Wallet Generated");
  console.log("=================================================");
  console.log("  Address:     ", wallet.address);
  console.log("  Private Key: ", wallet.privateKey);
  console.log("  Mnemonic:    ", wallet.mnemonic.phrase);
  console.log("=================================================");
  console.log("\nSTEPS:");
  console.log("1. Copy the Private Key above");
  console.log("2. Create paytkn-contracts/.env with:");
  console.log("   PRIVATE_KEY=<paste private key here>");
  console.log("3. Go to https://faucet.quicknode.com/base/sepolia");
  console.log("   Paste this address:", wallet.address);
  console.log("   Get free testnet ETH");
  console.log("4. Run: npx hardhat run scripts/deploy.js --network baseSepolia");
  console.log("\nWARNING: Save the mnemonic somewhere safe. Never commit .env to git.\n");
}

main().catch(console.error);
