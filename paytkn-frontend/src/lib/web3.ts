import { getDefaultConfig } from "@rainbow-me/rainbowkit";
import { baseSepolia } from "wagmi/chains";

export const config = getDefaultConfig({
  appName:   "PAYTKN",
  projectId: "paytkn-demo-2024",
  chains:    [baseSepolia],
  ssr:       true,
});

export const CONTRACT_ADDRESSES = {
  token:           "0xaeFa192cd89A25A1aE8fDE27196d25a64FC63402",
  staking:         "0xd26e03D2162e8c31BB9AD751Dcdf54CE8504165e",
  merchantStaking: "0xECAd8C1f99a1751584e5bba52e6CD28E3B8A3674",
  rewardEngine:    "0x81B1ed9b091C9Ff1a5Ef1C60eD6AF62e1c7054d5",
  treasury:        "0x819d6f1eC67E6a39359A238CcEDaf490153395F2",
};

/** Operator/deployer wallet — the backend uses this to relay on-chain payments */
export const OPERATOR_ADDRESS = "0x39F361208EFf8062aE46aCD5095815c0a420cb20";

/** Demo merchant address pre-filled in the live demo */
export const DEMO_MERCHANT = "0x39F361208EFf8062aE46aCD5095815c0a420cb20";

/**
 * PaytknGateway — deployed on Base Sepolia.
 * User calls pay(merchantAddr) with ETH value → merchant receives PAYTKN.
 * Rate: 3000 PAYTKN per 1 ETH.  Pre-funded with 500,000 PAYTKN.
 */
export const GATEWAY_ADDRESS = "0x9f470AF320a1dD38d4f9f3A4c00E2eF7e68aAa33" as const;
export const GATEWAY_RATE    = 3000; // PAYTKN per 1 ETH

export const GATEWAY_ABI = [
  {
    inputs: [{ name: "merchant", type: "address" }],
    name: "pay",
    outputs: [],
    stateMutability: "payable",
    type: "function",
  },
  {
    inputs: [{ name: "ethWei", type: "uint256" }],
    name: "previewPayment",
    outputs: [
      { name: "feeEth",           type: "uint256" },
      { name: "netEth",           type: "uint256" },
      { name: "paytknToMerchant", type: "uint256" },
    ],
    stateMutability: "view",
    type: "function",
  },
  {
    inputs: [],
    name: "ethToPaytknRate",
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
    type: "function",
  },
  {
    inputs: [],
    name: "totalPayments",
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
    type: "function",
  },
  {
    inputs: [],
    name: "totalPaytknSent",
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
    type: "function",
  },
  {
    inputs: [],
    name: "paytknBalance",
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
    type: "function",
  },
  {
    anonymous: false,
    inputs: [
      { indexed: true,  name: "user",             type: "address" },
      { indexed: true,  name: "merchant",          type: "address" },
      { indexed: false, name: "ethAmount",         type: "uint256" },
      { indexed: false, name: "feeEth",            type: "uint256" },
      { indexed: false, name: "paytknToMerchant",  type: "uint256" },
      { indexed: false, name: "timestamp",         type: "uint256" },
    ],
    name: "Payment",
    type: "event",
  },
] as const;

/** Minimal ERC-20 ABI — only what we need for balance reads */
export const ERC20_ABI = [
  {
    inputs: [{ name: "account", type: "address" }],
    name: "balanceOf",
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
    type: "function",
  },
  {
    inputs: [],
    name: "decimals",
    outputs: [{ name: "", type: "uint8" }],
    stateMutability: "view",
    type: "function",
  },
  {
    inputs: [],
    name: "symbol",
    outputs: [{ name: "", type: "string" }],
    stateMutability: "view",
    type: "function",
  },
] as const;
