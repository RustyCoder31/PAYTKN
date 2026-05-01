"use client";
import { useEffect, useState, useCallback } from "react";
import { useAccount, useSignMessage, useBalance, useReadContract } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { StatCard } from "@/components/StatCard";
import { api } from "@/lib/api";
import { CONTRACT_ADDRESSES, ERC20_ABI } from "@/lib/web3";

// ─── Types ────────────────────────────────────────────────────────────────────
type Tab = "overview" | "transactions" | "staking" | "rewards" | "referrals" | "subscriptions" | "settings";
type TxFilter = "all" | "payments" | "staking" | "rewards" | "trading";

const MOCK_TXS = [
  { id: "0xab12…ef34", type: "payment",  desc: "TechMart Store — MacBook Pro",     amount: "-$1,299",     paytkn: "+9.74 PAYTKN",  time: "2h ago",   status: "confirmed" },
  { id: "0xcd56…ab78", type: "staking",  desc: "Stake PAYTKN — 90 day lock",       amount: "-500 PAYTKN", paytkn: "Staking",       time: "1d ago",   status: "confirmed" },
  { id: "0xef90…cd12", type: "rewards",  desc: "Epoch 14 staking reward",          amount: "",            paytkn: "+12.5 PAYTKN",  time: "2d ago",   status: "confirmed" },
  { id: "0x1234…5678", type: "payment",  desc: "TechMart Store — AirPods Pro",     amount: "-$249",       paytkn: "+1.87 PAYTKN",  time: "3d ago",   status: "confirmed" },
  { id: "0x5678…9abc", type: "rewards",  desc: "Referral reward — Level 1 invite", amount: "",            paytkn: "+5.0 PAYTKN",   time: "4d ago",   status: "confirmed" },
  { id: "0x9abc…def0", type: "staking",  desc: "Unstake PAYTKN — flexible",        amount: "+200 PAYTKN", paytkn: "",              time: "5d ago",   status: "confirmed" },
  { id: "0xdef0…1234", type: "trading",  desc: "Buy PAYTKN on DEX",                amount: "-0.01 ETH",   paytkn: "+31 PAYTKN",   time: "6d ago",   status: "confirmed" },
];

const MOCK_SUBSCRIPTIONS = [
  { id: "sub_1", merchant: "TechMart Store", plan: "TechMart Pro", price: "$9.99/mo",  next_payment: "May 26, 2026", status: "active",   paytkn_bonus: 50 },
  { id: "sub_2", merchant: "CloudDev Tools", plan: "Developer Pro",price: "$19.99/mo", next_payment: "May 10, 2026", status: "active",   paytkn_bonus: 100 },
];

const RANK_TIERS = [
  { name: "Bronze",   min: 0,    color: "text-orange-400", bg: "bg-orange-500/10 border-orange-500/30" },
  { name: "Silver",   min: 500,  color: "text-gray-300",   bg: "bg-gray-500/10   border-gray-500/30" },
  { name: "Gold",     min: 2000, color: "text-yellow-400", bg: "bg-yellow-500/10 border-yellow-500/30" },
  { name: "Platinum", min: 5000, color: "text-indigo-300", bg: "bg-indigo-500/10 border-indigo-500/30" },
  { name: "Diamond",  min: 15000,color: "text-cyan-300",   bg: "bg-cyan-500/10   border-cyan-500/30" },
];

const TURBINE_REWARDS = [
  { icon: "📉", name: "Less Taxes",           desc: "Reduced protocol fees on all your payments",    cost: 200,  active: false },
  { icon: "2×", name: "2x Staking Rewards",   desc: "Double your epoch staking yield for 30 days",   cost: 500,  active: true  },
  { icon: "🆓", name: "Free Subscriptions",   desc: "1 month free on any subscribed merchant plan",  cost: 300,  active: false },
  { icon: "🎁", name: "Gift Cards",           desc: "Redeem PAYTKN for partner gift cards",          cost: 150,  active: false },
  { icon: "⭐", name: "Bonus Points",         desc: "1.5x points on every transaction for 2 weeks", cost: 100,  active: false },
];

// ─── Main Component ───────────────────────────────────────────────────────────
export default function UserDashboard() {
  const { address, isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();

  const [authState, setAuthState]   = useState<"idle" | "signing" | "done" | "error">("idle");
  const [jwt, setJwt]               = useState<string | null>(null);
  const [tab, setTab]               = useState<Tab>("overview");

  // ── Real on-chain balances (auto-refresh) ────────────────────────────────
  const { data: ethBal }    = useBalance({ address, query: { refetchInterval: 10000 } });
  const { data: paytknBal } = useReadContract({
    address: CONTRACT_ADDRESSES.token as `0x${string}`,
    abi: ERC20_ABI,
    functionName: "balanceOf",
    args: [address ?? "0x0000000000000000000000000000000000000000"],
    query: { enabled: !!address, refetchInterval: 10000 },
  });

  const paytknFormatted = paytknBal ? (Number(paytknBal) / 1e18).toFixed(4) : "—";
  const ethFormatted    = ethBal    ? parseFloat(ethBal.formatted).toFixed(5)    : "—";
  const [txFilter, setTxFilter]     = useState<TxFilter>("all");
  const [userData, setUserData]     = useState<any>(null);
  const [staking, setStaking]       = useState<any>(null);
  const [epochTimer, setEpochTimer] = useState(86400);
  const [stakeAmount, setStakeAmount] = useState("");
  const [cancelTarget, setCancelTarget] = useState<string | null>(null);
  const [turbineSpending, setTurbineSpending] = useState<string | null>(null);
  const [txs, setTxs]               = useState<typeof MOCK_TXS>(MOCK_TXS);
  const [seeded, setSeeded]         = useState(false);
  const [seeding, setSeeding]       = useState(false);

  // Epoch countdown
  useEffect(() => {
    const t = setInterval(() => setEpochTimer(p => Math.max(0, p - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  // Load data + try to get live history from backend
  useEffect(() => {
    api.stakingStats().then(setStaking).catch(() => {});
    if (address) {
      api.userProfile(address).then(setUserData).catch(() => {});
      // Fetch demo history (backend records live payments here)
      api.demoHistory(address).then((d: any) => {
        if (d.history && d.history.length > 0) {
          setTxs(d.history);
          setSeeded(d.seeded ?? false);
        }
      }).catch(() => {});
    }
  }, [address, jwt]);

  async function seedDemo() {
    setSeeding(true);
    try {
      await api.demoSeed();
      if (address) {
        const d: any = await api.demoHistory(address);
        if (d.history?.length > 0) { setTxs(d.history); setSeeded(true); }
      }
    } catch { /* backend may be offline */ }
    setSeeding(false);
  }

  // Auth flow: sign nonce
  async function authenticate() {
    if (!address) return;
    setAuthState("signing");
    try {
      const nonce = `PAYTKN_AUTH_${Date.now()}_${address.slice(-8)}`;
      await signMessageAsync({ message: nonce });
      setJwt(`jwt_demo_${address.slice(2, 12)}_${Date.now()}`);
      setAuthState("done");
    } catch {
      setAuthState("error");
      setTimeout(() => setAuthState("idle"), 2000);
    }
  }

  function fmtEpoch(s: number) {
    const h = Math.floor(s / 3600).toString().padStart(2, "0");
    const m = Math.floor((s % 3600) / 60).toString().padStart(2, "0");
    const sec = (s % 60).toString().padStart(2, "0");
    return `${h}:${m}:${sec}`;
  }

  const totalStaked = userData?.total_staked ?? 500;
  const totalRewards = userData?.total_rewards_earned ?? 47.5;
  const rankScore = totalStaked + totalRewards * 10;
  const rankIdx = RANK_TIERS.slice().reverse().findIndex(r => rankScore >= r.min);
  const rank = RANK_TIERS[rankIdx === -1 ? 0 : RANK_TIERS.length - 1 - rankIdx];
  const nextRank = RANK_TIERS[RANK_TIERS.length - 1 - rankIdx + 1] ?? null;
  const inviteCode = address ? `PAYTKN-${address.slice(2, 8).toUpperCase()}` : "PAYTKN-DEMO01";

  const filteredTxs = txFilter === "all" ? txs : txs.filter((t: any) => t.type === txFilter);

  const TABS: { key: Tab; label: string; icon: string }[] = [
    { key: "overview",       label: "Overview",      icon: "📊" },
    { key: "transactions",   label: "Transactions",  icon: "⚡" },
    { key: "staking",        label: "Staking",       icon: "🔒" },
    { key: "rewards",        label: "Rewards",       icon: "🏆" },
    { key: "referrals",      label: "Referrals",     icon: "👥" },
    { key: "subscriptions",  label: "Subscriptions", icon: "🔄" },
    { key: "settings",       label: "Settings",      icon: "⚙️" },
  ];

  // ── NOT CONNECTED ──────────────────────────────────────────────────────────
  if (!isConnected) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center">
        <div className="text-center space-y-6 max-w-md">
          <div className="text-7xl">👤</div>
          <div>
            <h1 className="text-3xl font-bold text-white">Your PAYTKN Dashboard</h1>
            <p className="text-gray-400 mt-2">Connect your wallet to view your balance, rewards, staking, referrals, and subscriptions.</p>
          </div>
          <ConnectButton />
        </div>
      </div>
    );
  }

  // ── WALLET CONNECTED, NOT AUTHENTICATED ───────────────────────────────────
  if (!jwt) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center">
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 max-w-md w-full text-center space-y-5">
          <div className="text-5xl">🔐</div>
          <div>
            <h2 className="text-xl font-bold text-white">Verify your identity</h2>
            <p className="text-gray-400 text-sm mt-2">
              Sign a nonce message with your wallet to authenticate. This is a free off-chain signature — no gas required.
            </p>
          </div>
          <div className="bg-gray-800 rounded-xl p-4 text-left text-sm space-y-1.5">
            <div className="flex justify-between"><span className="text-gray-500">Wallet</span><span className="text-white font-mono">{address?.slice(0,10)}…{address?.slice(-6)}</span></div>
            <div className="flex justify-between"><span className="text-gray-500">Chain</span><span className="text-white">Base Sepolia</span></div>
            <div className="flex justify-between"><span className="text-gray-500">Method</span><span className="text-indigo-400">eth_sign (nonce)</span></div>
          </div>
          {authState === "error" && <p className="text-red-400 text-sm">Signature rejected. Please try again.</p>}
          <button onClick={authenticate} disabled={authState === "signing"}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 text-white font-bold py-3.5 rounded-xl transition-colors flex items-center justify-center gap-2">
            {authState === "signing"
              ? <><div className="animate-spin h-4 w-4 rounded-full border-b-2 border-white" /> Waiting for signature…</>
              : "Sign & Enter Dashboard"}
          </button>
          <p className="text-xs text-gray-600">Signature issues a JWT session token — no blockchain transaction</p>
        </div>
      </div>
    );
  }

  // ── AUTHENTICATED DASHBOARD ───────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">My Dashboard</h1>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-gray-400 font-mono text-sm">{address?.slice(0,10)}…{address?.slice(-6)}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${rank.bg} ${rank.color} font-semibold`}>{rank.name}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!seeded && (
            <button onClick={seedDemo} disabled={seeding}
              className="flex items-center gap-1.5 text-xs bg-yellow-600/20 hover:bg-yellow-600/40 border border-yellow-500/30 text-yellow-400 px-3 py-1.5 rounded-full transition-colors disabled:opacity-50">
              {seeding ? "Loading…" : "🎮 Load Demo Data"}
            </button>
          )}
          <div className="flex items-center gap-2 text-xs text-green-400 bg-green-500/10 border border-green-500/20 rounded-full px-3 py-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            Authenticated via wallet signature
          </div>
        </div>
      </div>

      {/* Tab nav */}
      <div className="overflow-x-auto">
        <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-max">
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                tab === t.key ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white"}`}>
              <span className="text-xs">{t.icon}</span>{t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── OVERVIEW ── */}
      {tab === "overview" && (
        <div className="space-y-6">

          {/* Live on-chain wallet balances */}
          <div className="bg-gray-900 border border-indigo-800/40 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                <span className="text-xs text-green-400 font-medium uppercase tracking-widest">Live On-Chain Balances — Base Sepolia</span>
              </div>
              <a href={`https://sepolia.basescan.org/address/${address}`} target="_blank" rel="noopener noreferrer"
                className="text-xs text-gray-500 hover:text-gray-400">View on Basescan ↗</a>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-800/60 rounded-xl p-4">
                <p className="text-xs text-gray-500 mb-1">ETH Balance</p>
                <p className="font-mono text-xl font-bold text-white">{ethFormatted} <span className="text-sm text-gray-400">ETH</span></p>
                <p className="text-xs text-gray-600 mt-1">Base Sepolia testnet</p>
              </div>
              <div className="bg-indigo-900/30 border border-indigo-800/30 rounded-xl p-4">
                <p className="text-xs text-gray-500 mb-1">PAYTKN Balance</p>
                <p className="font-mono text-xl font-bold text-indigo-300">{paytknFormatted} <span className="text-sm text-gray-400">PAYTKN</span></p>
                <p className="text-xs text-gray-600 mt-1">Cashback from payments</p>
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                onClick={async () => {
                  try {
                    await (window as any).ethereum.request({
                      method: "wallet_watchAsset",
                      params: { type: "ERC20", options: { address: CONTRACT_ADDRESSES.token, symbol: "PAYTKN", decimals: 18 } },
                    });
                  } catch {}
                }}
                className="text-xs bg-indigo-800/30 hover:bg-indigo-700/40 border border-indigo-700/40 text-indigo-300 rounded-lg px-3 py-1.5 transition-colors"
              >
                + Add PAYTKN to MetaMask
              </button>
              <a href="/store" className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-400 rounded-lg px-3 py-1.5 transition-colors">
                🛍️ Go to Store
              </a>
              <a href="/demo" className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-400 rounded-lg px-3 py-1.5 transition-colors">
                ⚡ Live Demo
              </a>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="PAYTKN Balance"   value={paytknBal ? (Number(paytknBal) / 1e18).toFixed(2) : "—"} color="indigo" icon="⚡" sub="on-chain" />
            <StatCard label="Total Staked"     value={`${totalStaked.toLocaleString()}`}                        color="blue"   icon="🔒" sub="PAYTKN" />
            <StatCard label="Rewards Earned"   value={`${totalRewards.toFixed(2)}`}                             color="green"  icon="🎁" sub="PAYTKN lifetime" />
            <StatCard label="Active Subs"       value={MOCK_SUBSCRIPTIONS.length}                                color="purple" icon="🔄" sub="subscriptions" />
          </div>

          {/* Rank card */}
          <div className={`rounded-2xl border p-6 ${rank.bg}`}>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <div className="text-xs text-gray-500 mb-1">YOUR RANK</div>
                <div className={`text-3xl font-black ${rank.color}`}>{rank.name}</div>
                <div className="text-sm text-gray-400 mt-1">Score: <span className="text-white font-semibold">{rankScore.toLocaleString()}</span></div>
              </div>
              {nextRank && (
                <div className="text-right">
                  <div className="text-xs text-gray-500 mb-1">NEXT RANK</div>
                  <div className="text-lg font-bold text-white">{nextRank.name}</div>
                  <div className="text-xs text-gray-400">{(nextRank.min - rankScore).toLocaleString()} pts needed</div>
                  <div className="mt-2 h-1.5 w-32 bg-gray-800 rounded-full overflow-hidden">
                    <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${Math.min(100, (rankScore / nextRank.min) * 100)}%` }} />
                  </div>
                </div>
              )}
            </div>
            <div className="grid grid-cols-3 gap-3 mt-4 text-xs">
              <div className="bg-black/20 rounded-lg p-2.5 text-center"><div className="text-gray-400">TX Volume</div><div className="text-white font-bold mt-0.5">47 txns</div></div>
              <div className="bg-black/20 rounded-lg p-2.5 text-center"><div className="text-gray-400">Staking</div><div className="text-white font-bold mt-0.5">{totalStaked} PAYTKN</div></div>
              <div className="bg-black/20 rounded-lg p-2.5 text-center"><div className="text-gray-400">Subscriptions</div><div className="text-white font-bold mt-0.5">{MOCK_SUBSCRIPTIONS.length} active</div></div>
            </div>
          </div>

          {/* Recent activity */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-white">Recent Activity</h2>
              <button onClick={() => setTab("transactions")} className="text-xs text-indigo-400 hover:text-indigo-300">View all →</button>
            </div>
            <div className="space-y-2">
              {txs.slice(0, 4).map((tx: any) => (
                <div key={tx.id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                  <div>
                    <div className="text-sm text-white">{tx.desc}</div>
                    <div className="text-xs text-gray-500">{tx.time}</div>
                  </div>
                  <div className="text-right">
                    {tx.amount && <div className="text-sm text-gray-300">{tx.amount}</div>}
                    {tx.paytkn && <div className="text-xs text-indigo-400">{tx.paytkn}</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── TRANSACTIONS ── */}
      {tab === "transactions" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex gap-1 flex-wrap">
              {(["all","payments","staking","rewards","trading"] as TxFilter[]).map(f => (
                <button key={f} onClick={() => setTxFilter(f)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold capitalize transition-colors ${
                    txFilter === f ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}>
                  {f}
                </button>
              ))}
            </div>
            <button className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 px-3 py-1.5 rounded-lg transition-colors">
              📥 Export CSV
            </button>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-5 py-3">Description</th>
                  <th className="px-5 py-3">Type</th>
                  <th className="px-5 py-3">Amount</th>
                  <th className="px-5 py-3">PAYTKN</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {filteredTxs.map(tx => (
                  <tr key={tx.id} className="hover:bg-gray-800/40 transition-colors">
                    <td className="px-5 py-3.5">
                      <div className="text-white">{tx.desc}</div>
                      <div className="text-xs text-gray-500 font-mono">{tx.id}</div>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        tx.type === "payment"  ? "bg-blue-500/15 text-blue-400" :
                        tx.type === "staking"  ? "bg-purple-500/15 text-purple-400" :
                        tx.type === "rewards"  ? "bg-green-500/15 text-green-400" :
                        "bg-yellow-500/15 text-yellow-400"}`}>
                        {tx.type}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-gray-300">{tx.amount || "—"}</td>
                    <td className="px-5 py-3.5 text-indigo-400">{tx.paytkn || "—"}</td>
                    <td className="px-5 py-3.5">
                      <span className="text-xs text-green-400 bg-green-500/10 px-2 py-0.5 rounded-full">{tx.status}</span>
                    </td>
                    <td className="px-5 py-3.5 text-gray-500">{tx.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── STAKING ── */}
      {tab === "staking" && (
        <div className="space-y-5">
          {/* Epoch timer */}
          <div className="bg-indigo-900/30 border border-indigo-500/30 rounded-xl p-5 flex items-center justify-between">
            <div>
              <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">Next Epoch Reward</div>
              <div className="text-3xl font-black text-white font-mono">{fmtEpoch(epochTimer)}</div>
              <div className="text-xs text-indigo-400 mt-1">Rewards distributed every 24 hours</div>
            </div>
            <div className="text-right space-y-2">
              <StatCard label="Total Staked" value={`${totalStaked} PAYTKN`} color="blue" />
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            {/* Stake */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
              <h2 className="font-semibold text-white">Stake PAYTKN</h2>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label: "Flexible", days: 0,   mult: "1.0×", color: "bg-gray-600" },
                  { label: "30 Days",  days: 30,  mult: "1.2×", color: "bg-blue-600" },
                  { label: "90 Days",  days: 90,  mult: "1.5×", color: "bg-indigo-600" },
                  { label: "180 Days", days: 180, mult: "2.0×", color: "bg-purple-600" },
                ].map(tier => (
                  <div key={tier.days} className="bg-gray-800 rounded-xl p-3">
                    <div className={`inline-block text-xs text-white font-bold px-2 py-0.5 rounded ${tier.color} mb-1`}>{tier.label}</div>
                    <div className="text-xl font-bold text-white">{tier.mult}</div>
                    <div className="text-xs text-gray-400">multiplier</div>
                  </div>
                ))}
              </div>
              <input value={stakeAmount} onChange={e => setStakeAmount(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-indigo-500"
                placeholder="Amount to stake (PAYTKN)" type="number" />
              <button className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl transition-colors">
                Stake {stakeAmount || "0"} PAYTKN
              </button>
            </div>

            {/* Current stakes */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
              <h2 className="font-semibold text-white">Your Stakes</h2>
              {[
                { amount: 500,  lock: "90 Days",  mult: "1.5×", pending: 7.25,  ends: "Jun 15, 2026" },
                { amount: 200,  lock: "Flexible", mult: "1.0×", pending: 2.10,  ends: "Any time" },
              ].map((s, i) => (
                <div key={i} className="bg-gray-800 rounded-xl p-4 space-y-2">
                  <div className="flex justify-between">
                    <span className="font-bold text-white">{s.amount} PAYTKN</span>
                    <span className="text-xs bg-indigo-600/30 text-indigo-300 px-2 py-0.5 rounded-full">{s.lock} · {s.mult}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-400">Pending rewards</span>
                    <span className="text-green-400 font-semibold">{s.pending} PAYTKN</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-400">Unlocks</span>
                    <span className="text-gray-300">{s.ends}</span>
                  </div>
                  <div className="flex gap-2 mt-2">
                    <button className="flex-1 text-xs border border-gray-700 text-gray-400 hover:text-white py-1.5 rounded-lg transition-colors">Claim Rewards</button>
                    <button className="flex-1 text-xs border border-gray-700 text-gray-400 hover:text-white py-1.5 rounded-lg transition-colors">Unstake</button>
                  </div>
                </div>
              ))}
              <div className="text-xs text-gray-500 text-center">Next epoch: <span className="text-indigo-400 font-mono">{fmtEpoch(epochTimer)}</span></div>
            </div>
          </div>
        </div>
      )}

      {/* ── REWARDS ── */}
      {tab === "rewards" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="From Payments"   value="9.74 PAYTKN"  color="indigo" icon="⚡" />
            <StatCard label="From Staking"    value="19.35 PAYTKN" color="blue"   icon="🔒" />
            <StatCard label="From Referrals"  value="15.0 PAYTKN"  color="green"  icon="👥" />
            <StatCard label="Turbine Claimed" value="3.4 PAYTKN"   color="purple" icon="🌀" />
          </div>

          {/* Turbine rewards */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h2 className="font-semibold text-white mb-1">🌀 Turbine Rewards</h2>
            <p className="text-xs text-gray-400 mb-4">Token-gated perks — spend PAYTKN to activate. Coins returned after 24h.</p>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
              {TURBINE_REWARDS.map(r => (
                <div key={r.name} className={`rounded-xl border p-4 ${r.active ? "border-indigo-500/40 bg-indigo-500/10" : "border-gray-700"}`}>
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-2xl">{r.icon}</span>
                    {r.active && <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full">Active</span>}
                  </div>
                  <div className="font-semibold text-white text-sm">{r.name}</div>
                  <div className="text-xs text-gray-400 mt-1">{r.desc}</div>
                  <div className="flex items-center justify-between mt-3">
                    <span className="text-indigo-400 text-xs font-semibold">{r.cost} PAYTKN</span>
                    <button
                      onClick={() => setTurbineSpending(r.active ? null : r.name)}
                      className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                        r.active ? "bg-gray-700 text-gray-400" : "bg-indigo-600 hover:bg-indigo-500 text-white"}`}>
                      {r.active ? "Active" : "Activate"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
            {turbineSpending && (
              <div className="mt-4 bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 text-sm">
                <p className="text-yellow-400 font-semibold">Confirm activation of "{turbineSpending}"</p>
                <p className="text-gray-400 text-xs mt-1">PAYTKN will be held for 24 hours then returned to your wallet.</p>
                <div className="flex gap-2 mt-3">
                  <button onClick={() => setTurbineSpending(null)} className="px-4 py-1.5 border border-gray-700 text-gray-400 rounded-lg text-xs">Cancel</button>
                  <button onClick={() => setTurbineSpending(null)} className="px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-semibold">Confirm</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── REFERRALS ── */}
      {tab === "referrals" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Total Invites"   value="7"              color="green"  icon="👥" />
            <StatCard label="Active Referrals" value="4"             color="blue"   icon="✓" />
            <StatCard label="Referral Rewards" value="15 PAYTKN"    color="indigo" icon="🎁" />
            <StatCard label="Invite Depth"     value="Level 1-3"    color="purple" icon="🌲" />
          </div>

          {/* Invite code */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h2 className="font-semibold text-white mb-4">Your Invite Code</h2>
            <div className="flex gap-3 items-center mb-4">
              <code className="flex-1 bg-gray-800 rounded-xl px-5 py-4 text-2xl font-black text-indigo-400 tracking-widest text-center">
                {inviteCode}
              </code>
              <button onClick={() => navigator.clipboard.writeText(inviteCode)}
                className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-4 rounded-xl text-sm font-semibold transition-colors">
                Copy
              </button>
            </div>
            {/* QR code mock */}
            <div className="bg-white rounded-2xl p-4 w-32 h-32 mx-auto flex items-center justify-center">
              <div className="grid grid-cols-5 gap-0.5">
                {Array.from({length:25}).map((_,i) => (
                  <div key={i} className={`w-4 h-4 rounded-sm ${Math.random() > 0.5 ? "bg-gray-900" : "bg-white"}`} />
                ))}
              </div>
            </div>
            <p className="text-xs text-gray-500 text-center mt-3">Share your code — earn PAYTKN rewards for each level of your invite tree (max depth: 5)</p>
          </div>

          {/* Invite tiers */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h2 className="font-semibold text-white mb-4">Invite Tier Rewards</h2>
            <div className="space-y-3">
              {[
                { level: 1, desc: "Direct invites",           reward: "5 PAYTKN per sign-up + 1% of their fees lifetime" },
                { level: 2, desc: "Invites of your invites",  reward: "2 PAYTKN per sign-up + 0.5% of fees" },
                { level: 3, desc: "Level 3 tree",             reward: "1 PAYTKN per sign-up + 0.2% of fees" },
                { level: 4, desc: "Level 4 tree",             reward: "0.5 PAYTKN per sign-up" },
                { level: 5, desc: "Level 5 tree (max)",       reward: "0.25 PAYTKN per sign-up" },
              ].map(t => (
                <div key={t.level} className="flex items-start gap-4 bg-gray-800 rounded-xl px-4 py-3">
                  <div className="w-8 h-8 rounded-full bg-indigo-600 text-white text-sm font-bold flex items-center justify-center shrink-0">L{t.level}</div>
                  <div>
                    <div className="text-sm font-medium text-white">{t.desc}</div>
                    <div className="text-xs text-indigo-400 mt-0.5">{t.reward}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── SUBSCRIPTIONS ── */}
      {tab === "subscriptions" && (
        <div className="space-y-5">
          <h2 className="font-semibold text-white text-lg">Active Subscriptions</h2>
          {MOCK_SUBSCRIPTIONS.map(sub => (
            <div key={sub.id} className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-white">{sub.plan}</span>
                    <span className="text-xs bg-green-500/15 text-green-400 px-2 py-0.5 rounded-full">Active</span>
                  </div>
                  <div className="text-sm text-gray-400">{sub.merchant}</div>
                  <div className="mt-3 grid grid-cols-3 gap-3 text-xs">
                    <div><div className="text-gray-500">Price</div><div className="text-white font-semibold mt-0.5">{sub.price}</div></div>
                    <div><div className="text-gray-500">Next Payment</div><div className="text-white font-semibold mt-0.5">{sub.next_payment}</div></div>
                    <div><div className="text-gray-500">PAYTKN Bonus</div><div className="text-indigo-400 font-semibold mt-0.5">+{sub.paytkn_bonus}/period</div></div>
                  </div>
                </div>
                <button onClick={() => setCancelTarget(sub.id)}
                  className="text-xs border border-red-500/30 text-red-400 hover:bg-red-500/10 px-3 py-2 rounded-lg transition-colors whitespace-nowrap">
                  Cancel
                </button>
              </div>

              {cancelTarget === sub.id && (
                <div className="mt-4 bg-red-500/10 border border-red-500/20 rounded-xl p-4 space-y-3">
                  <p className="text-sm font-semibold text-red-400">Cancel {sub.plan}?</p>
                  <p className="text-xs text-gray-400">
                    Your subscription stays active until <strong className="text-white">{sub.next_payment}</strong>.
                    A partial refund will be issued to your wallet. The merchant will be notified.
                  </p>
                  <div className="bg-gray-800 rounded-lg p-3 text-xs space-y-1">
                    <div className="flex justify-between"><span className="text-gray-400">Subscription ends</span><span className="text-white">{sub.next_payment}</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">Refund amount</span><span className="text-green-400">Calculated on cancellation</span></div>
                    <div className="flex justify-between"><span className="text-gray-400">PAYTKN bonus lost</span><span className="text-yellow-400">Future bonuses forfeited</span></div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => setCancelTarget(null)} className="flex-1 border border-gray-700 text-gray-400 py-2 rounded-lg text-xs">Keep Subscription</button>
                    <button onClick={() => setCancelTarget(null)} className="flex-1 bg-red-600 hover:bg-red-500 text-white font-semibold py-2 rounded-lg text-xs transition-colors">Confirm Cancellation</button>
                  </div>
                </div>
              )}
            </div>
          ))}

          <a href="/store" className="flex items-center justify-center gap-2 border-2 border-dashed border-gray-700 hover:border-gray-600 rounded-xl p-5 text-gray-400 hover:text-white transition-colors">
            <span>+</span> Browse subscription plans at TechMart Store
          </a>
        </div>
      )}

      {/* ── SETTINGS ── */}
      {tab === "settings" && (
        <div className="space-y-5 max-w-lg">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
            <h2 className="font-semibold text-white">Account</h2>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between items-center py-3 border-b border-gray-800">
                <div><div className="text-white">Wallet Address</div><div className="text-xs text-gray-500 font-mono mt-0.5">{address}</div></div>
              </div>
              <div className="flex justify-between items-center py-3 border-b border-gray-800">
                <div><div className="text-white">Authentication</div><div className="text-xs text-gray-500 mt-0.5">Wallet signature (nonce-based)</div></div>
                <span className="text-xs text-green-400 bg-green-500/10 px-2 py-1 rounded-full">Active</span>
              </div>
              <div className="flex justify-between items-center py-3 border-b border-gray-800">
                <div><div className="text-white">Network</div><div className="text-xs text-gray-500 mt-0.5">Base Sepolia (Chain 84532)</div></div>
                <span className="text-xs text-indigo-400">Testnet</span>
              </div>
              <div className="flex justify-between items-center py-3">
                <div><div className="text-white">Notifications</div><div className="text-xs text-gray-500 mt-0.5">Payment confirmations, epoch rewards</div></div>
                <button className="text-xs bg-indigo-600 text-white px-3 py-1.5 rounded-lg">Configure</button>
              </div>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
            <h2 className="font-semibold text-white">Help & Support</h2>
            {[
              { label: "📚 FAQs", desc: "Common questions about PAYTKN" },
              { label: "💬 Live Chat", desc: "Talk to our support team" },
              { label: "✉️ Email Support", desc: "support@paytkn.io" },
              { label: "🐛 Report an Issue", desc: "Submit a system request" },
            ].map(item => (
              <button key={item.label} className="w-full flex items-center justify-between bg-gray-800 hover:bg-gray-700 rounded-xl px-4 py-3 transition-colors">
                <div className="text-left">
                  <div className="text-sm font-medium text-white">{item.label}</div>
                  <div className="text-xs text-gray-400">{item.desc}</div>
                </div>
                <span className="text-gray-600">→</span>
              </button>
            ))}
          </div>

          <button onClick={() => { setJwt(null); setAuthState("idle"); }}
            className="w-full border border-red-500/30 text-red-400 hover:bg-red-500/10 py-3 rounded-xl text-sm font-semibold transition-colors">
            Sign Out
          </button>
        </div>
      )}
    </div>
  );
}
