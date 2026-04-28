"use client";
import { useEffect, useState } from "react";
import { useAccount } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { StatCard } from "@/components/StatCard";
import { api } from "@/lib/api";

const TIERS = [
  { days: 0,   label: "Flexible", multiplier: "1.0x", color: "bg-gray-600" },
  { days: 30,  label: "30 Days",  multiplier: "1.2x", color: "bg-blue-600" },
  { days: 90,  label: "90 Days",  multiplier: "1.5x", color: "bg-indigo-600" },
  { days: 180, label: "180 Days", multiplier: "2.0x", color: "bg-purple-600" },
];

export default function StakingPage() {
  const { address, isConnected } = useAccount();
  const [stats, setStats]   = useState<any>(null);
  const [stakes, setStakes] = useState<any[]>([]);
  const [amount, setAmount] = useState("");
  const [tier, setTier]     = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.stakingStats().then(setStats).finally(() => setLoading(false));
    if (address) api.userBalance(address).then(console.log);
  }, [address]);

  useEffect(() => {
    if (address) api.userProfile(address).catch(() => {});
  }, [address]);

  if (loading) return <div className="flex justify-center h-64 items-center"><div className="animate-spin h-10 w-10 rounded-full border-b-2 border-indigo-500" /></div>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Staking</h1>
        <p className="text-gray-400 mt-1">Stake PAYTKN to earn emergent APY from protocol fees</p>
      </div>

      {/* Pool Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Staked"    value={`${Number(stats?.total_staked_paytkn ?? 0).toLocaleString()}`} color="indigo" sub="PAYTKN" />
        <StatCard label="Reward Pool"     value={`${Number(stats?.reward_pool_paytkn ?? 0).toLocaleString()}`}  color="green"  sub="PAYTKN" />
        <StatCard label="Current APY"     value={`${stats?.current_apy_pct ?? 0}%`}                             color="yellow" />
        <StatCard label="Unique Stakers"  value={stats?.unique_stakers ?? 0}                                     color="blue" />
      </div>

      {/* Lockup Tiers */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Lockup Tiers</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {TIERS.map((t, i) => (
            <button key={i} onClick={() => setTier(i)}
              className={`p-4 rounded-xl border-2 text-left transition-all ${
                tier === i ? "border-indigo-500 bg-indigo-500/10" : "border-gray-700 hover:border-gray-600"}`}>
              <div className={`inline-block px-2 py-0.5 rounded text-xs font-bold text-white mb-2 ${t.color}`}>{t.label}</div>
              <div className="text-2xl font-bold text-white">{t.multiplier}</div>
              <div className="text-xs text-gray-400 mt-1">reward multiplier</div>
            </button>
          ))}
        </div>
      </div>

      {/* Stake Form */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Stake PAYTKN</h2>
        {!isConnected ? (
          <div className="flex flex-col items-center gap-4 py-8">
            <p className="text-gray-400">Connect your wallet to stake</p>
            <ConnectButton />
          </div>
        ) : (
          <div className="space-y-4 max-w-md">
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Amount (PAYTKN)</label>
              <input value={amount} onChange={e => setAmount(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-indigo-500"
                placeholder="Enter amount..." type="number" />
            </div>
            <div className="bg-gray-800 rounded-lg p-4 text-sm space-y-2">
              <div className="flex justify-between"><span className="text-gray-400">Selected tier</span><span className="text-white">{TIERS[tier].label}</span></div>
              <div className="flex justify-between"><span className="text-gray-400">Multiplier</span><span className="text-indigo-400">{TIERS[tier].multiplier}</span></div>
              <div className="flex justify-between"><span className="text-gray-400">Lock period</span><span className="text-white">{TIERS[tier].days} days</span></div>
              <div className="flex justify-between"><span className="text-gray-400">Est. APY</span><span className="text-green-400">{((stats?.current_apy_pct ?? 0) * parseFloat(TIERS[tier].multiplier)).toFixed(1)}%</span></div>
            </div>
            <p className="text-xs text-yellow-500/80">⚠ Staking transactions require gas on Base Sepolia. This demo uses the backend operator wallet for simulation.</p>
            <button className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-lg transition-colors">
              Stake {amount || "0"} PAYTKN
            </button>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-3">How Staking Works</h2>
        <div className="grid md:grid-cols-3 gap-4 text-sm text-gray-400">
          <div><span className="text-indigo-400 font-semibold">Emergent APY</span><br />APY is not set manually — it emerges from reward_pool / total_staked × 365. The RL agent controls how much fee income flows into the pool.</div>
          <div><span className="text-indigo-400 font-semibold">Lockup Multiplier</span><br />Longer lockups earn more. 180-day stakers earn 2× more rewards than flexible stakers, incentivising long-term commitment.</div>
          <div><span className="text-indigo-400 font-semibold">Cashback Boost</span><br />Staking for 7+ days unlocks a staking boost on your cashback (up to +50%). The more you stake, the higher your payment rewards.</div>
        </div>
      </div>
    </div>
  );
}
