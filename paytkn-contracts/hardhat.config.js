require("@nomicfoundation/hardhat-ethers");
require("@nomicfoundation/hardhat-chai-matchers");
require("dotenv").config();

const PRIVATE_KEY  = process.env.PRIVATE_KEY    || "0x" + "0".repeat(64);
const BASESCAN_KEY = process.env.BASESCAN_API_KEY || "";

module.exports = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 }, viaIR: true },
  },
  networks: {
    baseSepolia: {
      url:      "https://sepolia.base.org",
      accounts: [PRIVATE_KEY],
      chainId:  84532,
    },
    sepolia: {
      url:      "https://ethereum-sepolia-rpc.publicnode.com",
      accounts: [PRIVATE_KEY],
      chainId:  11155111,
    },
    hardhat: { chainId: 31337 },
  },
  etherscan: {
    apiKey: { baseSepolia: BASESCAN_KEY },
    customChains: [{
      network:  "baseSepolia",
      chainId:  84532,
      urls: {
        apiURL:     "https://api-sepolia.basescan.org/api",
        browserURL: "https://sepolia.basescan.org",
      },
    }],
  },
};
