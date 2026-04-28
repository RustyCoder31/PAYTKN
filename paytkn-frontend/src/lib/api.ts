const API       = process.env.NEXT_PUBLIC_API_URL       || "http://localhost:8000";
const MODEL_API = process.env.NEXT_PUBLIC_MODEL_API_URL || "http://localhost:8001";

async function get(base: string, path: string) {
  const res = await fetch(`${base}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

async function post(base: string, path: string, body: unknown = {}) {
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

// ── Backend (port 8000) ───────────────────────────────────────────────────────
export const api = {
  health:        () => get(API, "/health"),
  protocolState: () => get(API, "/protocol/state"),
  price:         () => get(API, "/protocol/price"),
  supply:        () => get(API, "/protocol/supply"),
  agentObserve:  () => get(API, "/agent/observe"),
  stakingStats:  () => get(API, "/staking/stats"),
  merchantStats: () => get(API, "/staking/merchant/stats"),
  paymentStats:  () => get(API, "/payments/stats"),
  userProfile:   (addr: string) => get(API, `/users/${addr}/profile`),
  userBalance:   (addr: string) => get(API, `/users/${addr}/balance`),
  merchantTier:  (addr: string) => get(API, `/staking/merchant/${addr}/tier`),

  processPayment: (user: string, merchant: string, amount_eth: number) =>
    post(API, "/payments/process", { user_address: user, merchant_address: merchant, amount_eth }),

  updateParams: (params: {
    mint_factor: number; burn_rate_bps: number; reward_alloc_bps: number;
    cashback_base_bps: number; merchant_alloc_bps: number; treasury_ratio_bps: number;
  }) => post(API, "/agent/update-params", params),

  registerUser: (address: string, invited_by?: string) =>
    post(API, "/users/register", { address, invited_by: invited_by || "0x0000000000000000000000000000000000000000" }),

  triggerBurn: () => post(API, "/agent/burn", {}),
  triggerMint: (amount: number) => post(API, `/agent/mint?amount_paytkn=${amount}`, {}),

  // Demo / economy seed
  demoSeed:    ()             => post(API, "/demo/seed", {}),
  demoHistory: (addr: string) => get(API, `/demo/history/${addr}`),
  demoEconomy: ()             => get(API, "/demo/economy"),

  // Economy simulation
  simState:  () => get(API, "/simulation/state"),
  simFeed:   () => get(API, "/simulation/feed"),
  simStart:  () => post(API, "/simulation/start"),
  simStop:   () => post(API, "/simulation/stop"),
  simReset:  () => post(API, "/simulation/reset"),
};

// ── RL Model Server (port 8001) ───────────────────────────────────────────────
export const modelApi = {
  status:    ()         => get(MODEL_API, "/status"),
  predict:   ()         => get(MODEL_API, "/predict"),
  step:      ()         => post(MODEL_API, "/step"),
  startLoop: ()         => post(MODEL_API, "/start"),
  stopLoop:  ()         => post(MODEL_API, "/stop"),
};
