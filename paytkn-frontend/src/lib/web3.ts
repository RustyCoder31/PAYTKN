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
