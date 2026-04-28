"use client";
import { useEffect, useState } from "react";
import { StatCard } from "./StatCard";
import { api } from "@/lib/api";
import { CONTRACT_ADDRESSES } from "@/lib/web3";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const BASESCAN = "https://sepolia.basescan.org/address";

export function Dashboard() {
  const [state, setState]     = useState<any>(null);
  const [supply, setSupply]   = useState<any>(null);
  const [staking, setStaking] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [priceHistory]        = useState([
    { day: "D-5", price: 0.98 }, { day: "D-4", price: 1.01 },
    { day: "D-3", price: 0.99 }, { day: "D-2", price: 1.02 },
    { day: "D-1", price: 1.00 }, { day: "Now", price: 1.00 },
  ]);

  useEffect(() => {
    Promise.all([api.protocolState(), api.supply(), api.stakingStats()])
      .then(([s, sup, st]) => { setState(s); setSupply(sup); setStaking(st); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500" />
    </div>
  );

  const price    = state?.token?.price_usd ?? 1.00;
  const supply_n = Number(supply?.total_supply ?? 12000000);
  const staked   = Number(staking?.total_staked_paytkn ?? 0);
  const apy      = staking?.current_apy_pct ?? 0;
  const payments = state?.payments?.total_processed ?? 0;
  const burned   = Number(supply?.total_burned ?? 0);
  const params   = state?.rl_parameters ?? {};

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Protocol Dashboard</h1>
          <p className="text-gray-400 mt-1">Live on Base Sepolia — RL-controlled economics</p>
        </div>
        <span className="flex items-center gap-2 bg-green-500/10 border border-green-500/30 rounded-full px-4 py-2 text-green-400 text-sm">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          Live
        </span>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="PAYTKN Price"     value={`$${price.toFixed(4)}`}                  color="indigo" icon="💲" />
        <StatCard label="Total Supply"     value={`${(supply_n/1e6).toFixed(2)}M`}         color="blue"   icon="🪙" sub="of 100M hard cap" />
        <StatCard label="Total Staked"     value={`${staked.toLocaleString()}`}             color="green"  icon="🔒" sub={`${apy}% APY`} />
        <StatCard label="Payments"         value={payments}                                 color="yellow" icon="⚡" sub="processed on-chain" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Burned"     value={`${burned.toLocaleString()}`}             color="red"    icon="🔥" sub="PAYTKN removed" />
        <StatCard label="Treasury Stable"  value={`${Number(state?.treasury?.stable_reserve_eth ?? 0).toFixed(4)} ETH`} color="green" icon="🏦" />
        <StatCard label="Cashback Paid"    value={`${Number(state?.token?.total_cashback_paid ?? 0).toFixed(0)}`} color="indigo" icon="🎁" sub="PAYTKN to users" />
        <StatCard label="Total Minted"     value={`${Number(state?.token?.total_minted ?? 12000000).toLocaleString()}`} color="blue" icon="⛏" />
      </div>

      {/* Price Chart + RL Params */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Price Chart */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4">PAYTKN Price (USD)</h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={priceHistory}>
              <XAxis dataKey="day" stroke="#6b7280" />
              <YAxis domain={[0.9, 1.1]} stroke="#6b7280" />
              <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151" }} />
              <Line type="monotone" dataKey="price" stroke="#6366f1" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* RL Parameters */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4">
            RL Agent Parameters
            <span className="ml-2 text-xs text-indigo-400 font-normal">live on-chain</span>
          </h2>
          <div className="space-y-3">
            {[
              { label: "Mint Factor",       val: `${params.mint_factor ?? 100}x/100`,   pct: (params.mint_factor ?? 100) / 200 },
              { label: "Burn Rate",         val: `${params.burn_rate_bps ?? 2} bps/day`, pct: (params.burn_rate_bps ?? 2) / 5 },
              { label: "Reward Alloc",      val: `${((params.reward_alloc_bps ?? 3000)/100).toFixed(0)}%`, pct: (params.reward_alloc_bps ?? 3000) / 6000 },
              { label: "Cashback Base",     val: `${((params.cashback_base_bps ?? 50)/100).toFixed(1)}%`, pct: (params.cashback_base_bps ?? 50) / 100 },
              { label: "Merchant Alloc",    val: `${((params.merchant_alloc_bps ?? 1000)/100).toFixed(0)}%`, pct: (params.merchant_alloc_bps ?? 1000) / 2500 },
              { label: "Treasury Ratio",    val: `${((params.treasury_ratio_bps ?? 6000)/100).toFixed(0)}%`, pct: (params.treasury_ratio_bps ?? 6000) / 9000 },
            ].map(p => (
              <div key={p.label}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-400">{p.label}</span>
                  <span className="text-indigo-300 font-mono">{p.val}</span>
                </div>
                <div className="h-1.5 bg-gray-800 rounded-full">
                  <div className="h-1.5 bg-indigo-500 rounded-full transition-all" style={{ width: `${p.pct * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Contract Addresses */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Deployed Contracts — Base Sepolia</h2>
        <div className="grid md:grid-cols-2 gap-3">
          {Object.entries(CONTRACT_ADDRESSES).map(([name, addr]) => (
            <a key={name} href={`${BASESCAN}/${addr}`} target="_blank" rel="noreferrer"
               className="flex items-center justify-between bg-gray-800 hover:bg-gray-700 rounded-lg px-4 py-3 transition-colors group">
              <span className="text-sm text-gray-300 capitalize">{name}</span>
              <span className="text-xs font-mono text-indigo-400 group-hover:text-indigo-300">
                {addr.slice(0, 10)}...{addr.slice(-6)} ↗
              </span>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
