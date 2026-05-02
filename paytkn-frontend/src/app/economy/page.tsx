"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { Orbitron, Space_Mono } from "next/font/google";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, LineChart, Line,
} from "recharts";
import { api } from "@/lib/api";

const orbitron  = Orbitron({ subsets: ["latin"], weight: ["700", "900"] });
const spaceMono = Space_Mono({ subsets: ["latin"], weight: ["400", "700"] });

// ── Types ─────────────────────────────────────────────────────────────────────
interface DecisionEntry {
  id: string;
  day: number;
  param: string;
  oldVal: number;
  newVal: number;
  direction: "up" | "down";
  action: string;
  icon: string;
  reason: string;
  ts: string;
}

interface TxEvent {
  id: number; day?: number; tick?: number; type: string; desc: string;
  amount_usd: number; paytkn: number; color: string; ts: string;
}
interface TopUser  { id: string; archetype: string; emoji: string; wallet: number; staked: number; txs: number; volume: number; loyalty: number; }
interface TopMerch { id: string; name: string; archetype: string; emoji: string; wallet: number; staked: number; volume: number; tx_count: number; loan_balance: number; }
interface SimState {
  day: number; tick?: number; running: boolean;
  token_price_usd: number;
  price_history: Array<{ day?: number; tick?: number; price: number; ts: string }>;
  total_supply: number;
  supply_history: Array<{ day?: number; tick?: number; supply: number; staked?: number; active_users?: number }>;
  daily_stats: Array<{ day: number; price: number; txs: number; volume: number; burned: number; active_users: number; sentiment: number; staking_ratio: number }>;
  treasury_eth: number; treasury_paytkn: number; treasury_stable: number; treasury_value_usd: number;
  staking_pool: number; reward_pool: number; current_apy_pct: number; staking_ratio_pct: number;
  total_payments: number; total_volume_usd: number;
  total_cashback: number; total_burned: number; total_minted: number;
  total_staking_rewards: number;
  tx_feed: TxEvent[];
  top_users: TopUser[];
  top_merchants: TopMerch[];
  // legacy fields (old 5-user sim)
  users?: Record<string, any>;
  merchants?: Record<string, any>;
  epoch?: number;
  rl_params: Record<string, number>;
  // population
  active_users: number; total_users: number; active_merchants: number; total_merchants: number;
  sentiment: number; archetype_breakdown: Record<string, number>;
  market_cap: number; price_volatility: number;
  lp_paytkn: number; lp_stable: number; lp_depth: number;
}

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  bg:      "#020509",
  panel:   "#05090f",
  border:  "#0c1a2e",
  borderB: "#132540",
  cyan:    "#06b6d4",
  cyanDim: "#0e3d4d",
  green:   "#22c55e",
  red:     "#ef4444",
  purple:  "#a855f7",
  amber:   "#f59e0b",
  orange:  "#f97316",
  text:    "#94a3b8",
  textB:   "#e2e8f0",
  dim:     "#1e3252",
  dimmer:  "#0d1f38",
};

const TX_COLOR: Record<string, string> = {
  payment: T.cyan, staking: T.purple, reward: T.green,
  burn: T.red, trading: T.amber, mint: T.green,
};
const TX_BG: Record<string, string> = {
  payment: "rgba(6,182,212,0.07)", staking: "rgba(168,85,247,0.07)",
  reward:  "rgba(34,197,94,0.07)", burn:    "rgba(239,68,68,0.07)",
  trading: "rgba(245,158,11,0.07)", mint:   "rgba(34,197,94,0.07)",
};
const PARAM_MAX: Record<string, number> = {
  mint_factor: 200, burn_rate_bps: 50, reward_alloc_bps: 6000,
  cashback_base_bps: 100, merchant_alloc_bps: 2500, treasury_ratio_bps: 9000,
  staking_apy_pct: 25,
};
const PARAM_LABEL: Record<string, string> = {
  mint_factor: "Mint Factor", burn_rate_bps: "Burn Rate",
  reward_alloc_bps: "Staking Reward", cashback_base_bps: "Cashback Base",
  merchant_alloc_bps: "Merchant Alloc", treasury_ratio_bps: "Treasury Ratio",
  staking_apy_pct: "Staking APY",
};
// Keys to skip — derived values or internal, not RL levers
const PARAM_SKIP = new Set(["staking_apy_pct"]);

// ── AI Decision log helpers ───────────────────────────────────────────────────
const PARAM_ACTION: Record<string, { up: string; down: string }> = {
  burn_rate_bps:      { up: "Increased Burn Rate",       down: "Reduced Burn Rate"       },
  mint_factor:        { up: "Increased Mint Output",     down: "Reduced Mint Output"     },
  cashback_base_bps:  { up: "Boosted User Cashback",     down: "Trimmed User Cashback"   },
  reward_alloc_bps:   { up: "Boosted Staking Rewards",   down: "Cut Staking Rewards"     },
  merchant_alloc_bps: { up: "Increased Merchant Alloc",  down: "Cut Merchant Alloc"      },
  treasury_ratio_bps: { up: "Raised Treasury Ratio",     down: "Lowered Treasury Ratio"  },
};
const PARAM_ICON: Record<string, { up: string; down: string }> = {
  burn_rate_bps:      { up: "🔥", down: "💧" },
  mint_factor:        { up: "⛏️", down: "📉" },
  cashback_base_bps:  { up: "🎁", down: "✂️" },
  reward_alloc_bps:   { up: "🚀", down: "📉" },
  merchant_alloc_bps: { up: "🏪", down: "✂️" },
  treasury_ratio_bps: { up: "🏦", down: "📤" },
};

function generateReason(param: string, oldVal: number, newVal: number, sim: SimState): string {
  const up   = newVal > oldVal;
  const p    = sim.token_price_usd;
  const sent = sim.sentiment;
  const sr   = sim.staking_ratio_pct ?? 0;

  switch (param) {
    case "burn_rate_bps":
      return up
        ? p < 0.99
          ? `Price slipped to $${p.toFixed(4)} — below $1.00 peg. Agent raised burn rate to shrink circulating supply and push price back up.`
          : `Supply growing faster than demand. Agent increased burn rate per transaction to apply deflationary pressure and protect peg.`
        : `Price stable near $${p.toFixed(4)}. Agent eased burn rate to avoid over-deflation and preserve healthy liquidity for users.`;

    case "mint_factor":
      return up
        ? `Staking reward pool running low. Agent raised mint output to replenish emissions and keep staking APY attractive for long-term holders.`
        : p < 0.98
          ? `Price at $${p.toFixed(4)} — below peg. Agent cut minting to tighten supply and support price recovery.`
          : `Supply metrics healthy. Agent reduced mint factor to prevent token dilution and protect per-token value.`;

    case "cashback_base_bps":
      return up
        ? sent < 0.45
          ? `Bearish market sentiment at ${(sent * 100).toFixed(0)}%. Agent boosted cashback rewards to incentivise spending and rebuild positive user momentum.`
          : `Transaction volume slowing. Agent raised cashback to make every payment more rewarding and drive network activity.`
        : `Activity metrics strong — cashback was over-rewarding. Agent trimmed it to preserve treasury reserves for volatile periods.`;

    case "reward_alloc_bps":
      return up
        ? sr < 25
          ? `Staking ratio low at ${sr.toFixed(1)}%. Agent reallocated more protocol revenue to stakers to encourage locking and reduce liquid sell pressure.`
          : `Agent increased staking yield to attract long-term holders, slow token velocity, and reinforce price stability.`
        : `Staking ratio healthy at ${sr.toFixed(1)}%. Agent shifted allocation toward cashback and treasury to improve capital efficiency across the protocol.`;

    case "merchant_alloc_bps":
      return up
        ? `Merchant payment volume declining. Agent increased merchant allocation to attract more businesses and widen the payment network.`
        : `Merchant ecosystem active and well-incentivised. Agent trimmed allocation to redirect capital toward user cashback and staking rewards.`;

    case "treasury_ratio_bps":
      return up
        ? p < 0.95
          ? `Price critically low at $${p.toFixed(4)}. Agent is building treasury reserves to enable a potential buyback and defend the peg.`
          : `Agent directing more revenue to treasury to build a volatility buffer ahead of uncertain market conditions.`
        : `Treasury reserves adequate. Agent reduced allocation to free capital for user-facing incentives that drive protocol growth.`;

    default:
      return up
        ? `Parameter raised in response to current network conditions per the PPO agent's optimization signal.`
        : `Parameter lowered to rebalance protocol economics following the PPO agent's latest policy update.`;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const n  = (v: number, d = 2) => (v ?? 0).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
const nk = (v: number) => v >= 1e6 ? `${(v/1e6).toFixed(2)}M` : v >= 1e3 ? `${(v/1e3).toFixed(1)}k` : (v ?? 0).toFixed(1);
const usd = (v: number) => `$${n(v)}`;

// ── Custom tooltips ───────────────────────────────────────────────────────────
function PriceTip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const v = payload[0].value as number;
  return (
    <div style={{ background: T.panel, border: `1px solid ${T.border}`, padding: "6px 10px", borderRadius: 4 }}>
      <div className={spaceMono.className} style={{ color: v >= 1 ? T.green : T.red, fontSize: 13, fontWeight: 700 }}>
        ${v.toFixed(6)}
      </div>
      <div style={{ color: T.dim, fontSize: 10 }}>day {payload[0].payload?.day ?? payload[0].payload?.tick}</div>
    </div>
  );
}

// ── Pulsing LED ───────────────────────────────────────────────────────────────
function LED({ color, pulse }: { color: string; pulse?: boolean }) {
  return (
    <span style={{
      display: "inline-block", width: 7, height: 7, borderRadius: "50%",
      background: color, boxShadow: pulse ? `0 0 6px ${color}` : "none",
      animation: pulse ? "led-pulse 1.4s ease-in-out infinite" : "none",
    }} />
  );
}

// ── Metric card ───────────────────────────────────────────────────────────────
function MCard({ label, value, sub, color = T.cyan }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 6, padding: "12px 14px" }}>
      <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim, marginBottom: 5 }}>{label}</div>
      <div className={spaceMono.className} style={{ fontSize: 18, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: T.text, marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function EconomyPage() {
  const [sim, setSim]             = useState<SimState | null>(null);
  const [running, setRunning]     = useState(false);
  const [prevP, setPrevP]         = useState(1.0);
  const [backOk, setBackOk]       = useState(true);
  const [decisions, setDecisions] = useState<DecisionEntry[]>([]);
  const prevPRef      = useRef(1.0);
  const prevParamsRef = useRef<Record<string, number>>({});

  const loadState = useCallback(async () => {
    try {
      const s: SimState = await api.simState();

      // ── Detect RL param changes and build decision log entries ──────────
      const newParams = s.rl_params ?? {};
      const oldParams = prevParamsRef.current;
      if (Object.keys(oldParams).length > 0) {
        const newEntries: DecisionEntry[] = [];
        for (const [key, newVal] of Object.entries(newParams)) {
          if (PARAM_SKIP.has(key)) continue;
          const oldVal = oldParams[key];
          if (oldVal !== undefined && Math.abs(newVal - oldVal) >= 1) {
            const dir = newVal > oldVal ? "up" : "down";
            const actions = PARAM_ACTION[key] ?? { up: "Adjusted up", down: "Adjusted down" };
            const icons   = PARAM_ICON[key]   ?? { up: "⚙️", down: "⚙️" };
            newEntries.push({
              id:        `${key}-${Date.now()}-${Math.random()}`,
              day:       s.day ?? s.tick ?? 0,
              param:     key,
              oldVal,
              newVal,
              direction: dir,
              action:    actions[dir],
              icon:      icons[dir],
              reason:    generateReason(key, oldVal, newVal, s),
              ts:        new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
            });
          }
        }
        if (newEntries.length > 0) {
          setDecisions(prev => [...newEntries, ...prev].slice(0, 30));
        }
      }
      prevParamsRef.current = { ...newParams };

      setSim(prev => {
        if (prev) { setPrevP(prev.token_price_usd); prevPRef.current = prev.token_price_usd; }
        return s;
      });
      setRunning(s.running);
      setBackOk(true);
    } catch { setBackOk(false); }
  }, []);

  // Auto-start + poll every 2.5 s
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const s: SimState = await api.simState();
        if (mounted && !s.running) { await api.simStart(); }
        if (mounted) { setSim(s); setRunning(true); }
      } catch {}
    })();
    const t = setInterval(() => { if (mounted) loadState(); }, 2500);
    return () => { mounted = false; clearInterval(t); };
  }, [loadState]);

  async function start() { try { await api.simStart(); setRunning(true); } catch {} }
  async function stop()  { try { await api.simStop();  setRunning(false); } catch {} }
  async function reset() {
    try {
      await api.simReset();
      setSim(null);
      setRunning(false);
      setDecisions([]);
      prevParamsRef.current = {};
    } catch {}
  }

  const price        = sim?.token_price_usd ?? 1.0;
  const priceUp      = price >= prevPRef.current;
  const pricePct     = ((price - 1.0) / 1.0) * 100;
  const phData       = (sim?.price_history ?? []).slice(-120);
  const shData       = (sim?.supply_history ?? []).slice(-120).map(d => ({ ...d, supplyM: +(d.supply / 1_000_000).toFixed(4) }));
  const feed         = sim?.tx_feed ?? [];
  const topUsers     = sim?.top_users ?? [];
  const topMerchants = sim?.top_merchants ?? [];
  const params       = sim?.rl_params ?? {};
  const archBreak    = sim?.archetype_breakdown ?? {};
  const sentiment    = sim?.sentiment ?? 0.5;
  // Treasury display — prefer stable+paytkn from new sim, fallback for old
  const treasuryUsd  = sim?.treasury_value_usd ?? ((sim?.treasury_eth ?? 0) * 3100 + (sim?.treasury_paytkn ?? 0));
  const treasuryStable = sim?.treasury_stable ?? ((sim?.treasury_eth ?? 0) * 3100);
  const treasuryPct  = Math.min(100, treasuryUsd / 20_000_000 * 100);  // % of 20M USD target
  const simDay       = sim?.day ?? sim?.tick ?? 0;

  return (
    <div style={{ background: T.bg, minHeight: "100vh", color: T.text }}>

      {/* Global styles */}
      <style>{`
        @keyframes led-pulse { 0%,100%{opacity:1} 50%{opacity:0.25} }
        @keyframes row-in { from{opacity:0;transform:translateY(-6px)} to{opacity:1;transform:translateY(0)} }
        ::-webkit-scrollbar { width: 3px; height: 3px; }
        ::-webkit-scrollbar-track { background: ${T.bg}; }
        ::-webkit-scrollbar-thumb { background: ${T.border}; border-radius: 99px; }
        .sim-feed-row:first-child { animation: row-in 0.35s ease; }
      `}</style>

      {/* Subtle grid backdrop */}
      <div style={{
        position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0,
        backgroundImage: `linear-gradient(${T.dimmer}88 1px, transparent 1px),linear-gradient(90deg, ${T.dimmer}88 1px, transparent 1px)`,
        backgroundSize: "36px 36px",
        maskImage: "radial-gradient(ellipse 80% 60% at 50% 0%, black 40%, transparent 100%)",
      }} />

      <div style={{ position: "relative", zIndex: 1 }}>

        {/* ══ HEADER ══════════════════════════════════════════════════════════ */}
        <div style={{
          background: "rgba(5,9,15,0.96)", borderBottom: `1px solid ${T.border}`,
          backdropFilter: "blur(16px)", padding: "10px 24px",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap",
        }}>
          {/* Left: title + status */}
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <div className={orbitron.className} style={{ fontSize: 13, letterSpacing: "0.2em", color: T.cyan, fontWeight: 900 }}>
              PAYTKN · ECONOMY SIMULATOR
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {[
                { label: "DAY",     value: String(simDay),                                      color: T.cyan },
                { label: "USERS",   value: `${sim?.active_users ?? 0}/${sim?.total_users ?? 0}`,color: T.green },
                { label: "MERCHANTS",value: String(sim?.active_merchants ?? 0),                 color: T.amber },
                { label: "SENTIMENT",value: `${(sentiment * 100).toFixed(0)}%`,                 color: sentiment > 0.6 ? T.green : sentiment < 0.4 ? T.red : T.amber },
              ].map(b => (
                <div key={b.label} style={{ display: "flex", gap: 5, alignItems: "center", padding: "3px 9px", border: `1px solid ${T.border}`, borderRadius: 4, background: T.panel }}>
                  <span style={{ fontSize: 9, letterSpacing: "0.12em", color: T.dim }}>{b.label}</span>
                  <span className={spaceMono.className} style={{ fontSize: 12, fontWeight: 700, color: b.color }}>{b.value}</span>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <LED color={running ? T.green : T.red} pulse={running} />
              <span style={{ fontSize: 10, letterSpacing: "0.14em", color: running ? T.green : T.red, fontWeight: 700 }}>
                {running ? "LIVE" : "PAUSED"}
              </span>
              {!backOk && <span style={{ fontSize: 9, color: T.red, marginLeft: 8 }}>⚠ BACKEND OFFLINE</span>}
            </div>
          </div>

          {/* Right: controls */}
          <div style={{ display: "flex", gap: 6 }}>
            {[
              { label: running ? "⏹ STOP" : "▶ START", action: running ? stop : start, color: running ? T.red : T.green },
              { label: "↺ RESET", action: reset, color: T.amber },
            ].map(btn => (
              <button key={btn.label} onClick={btn.action} style={{
                padding: "6px 16px", borderRadius: 5, fontSize: 11, fontWeight: 700,
                letterSpacing: "0.08em", cursor: "pointer", fontFamily: "inherit",
                background: `${btn.color}18`, border: `1px solid ${btn.color}55`, color: btn.color,
                transition: "all 0.15s",
              }}>
                {btn.label}
              </button>
            ))}
          </div>
        </div>

        {/* ══ MAIN GRID ═══════════════════════════════════════════════════════ */}
        <div style={{ padding: "16px 20px", display: "grid", gridTemplateColumns: "240px 1fr 264px", gap: 14 }}>

          {/* ── LEFT COLUMN ──────────────────────────────────────────────── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>

            {/* Price */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim, marginBottom: 8 }}>PAYTKN / USD</div>
              <div className={spaceMono.className} style={{
                fontSize: 38, fontWeight: 700, lineHeight: 1,
                color: priceUp ? T.green : T.red,
                textShadow: `0 0 20px ${priceUp ? T.green : T.red}44`,
                transition: "color 0.4s",
              }}>
                ${price.toFixed(4)}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 7 }}>
                <span style={{ color: pricePct >= 0 ? T.green : T.red, fontSize: 12 }}>
                  {pricePct >= 0 ? "▲" : "▼"} {Math.abs(pricePct).toFixed(4)}%
                </span>
                <span style={{ color: T.dim, fontSize: 10 }}>vs $1.00 peg</span>
              </div>
              <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7 }}>
                {[
                  { l: "APY",      v: `${(sim?.current_apy_pct ?? 12).toFixed(1)}%`, c: T.green },
                  { l: "VOLATILITY",v: `${((sim?.price_volatility ?? 0) * 100).toFixed(3)}%`, c: T.amber },
                ].map(x => (
                  <div key={x.l} style={{ padding: "7px 8px", background: "#030609", borderRadius: 4 }}>
                    <div style={{ fontSize: 9, color: T.dim, letterSpacing: "0.1em" }}>{x.l}</div>
                    <div className={spaceMono.className} style={{ fontSize: 14, color: x.c, marginTop: 2, fontWeight: 700 }}>{x.v}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 7, padding: "7px 8px", background: "#030609", borderRadius: 4 }}>
                <div style={{ fontSize: 9, color: T.dim, letterSpacing: "0.1em", marginBottom: 2 }}>MARKET CAP</div>
                <div className={spaceMono.className} style={{ fontSize: 13, color: T.cyan, fontWeight: 700 }}>${nk(sim?.market_cap ?? 0)}</div>
              </div>
            </div>

            {/* Treasury */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim, marginBottom: 8 }}>TREASURY</div>
              <div className={spaceMono.className} style={{ fontSize: 22, color: T.amber, fontWeight: 700 }}>
                ${nk(treasuryUsd)}
              </div>
              <div style={{ fontSize: 9, color: T.dim, marginBottom: 10 }}>total value</div>
              <div style={{ height: 5, background: "#030609", borderRadius: 99, overflow: "hidden", marginBottom: 5 }}>
                <div style={{
                  height: "100%", width: `${treasuryPct}%`, borderRadius: 99,
                  background: `linear-gradient(90deg, #b45309, ${T.amber})`,
                  transition: "width 1.2s ease",
                  boxShadow: `0 0 8px ${T.amber}55`,
                }} />
              </div>
              <div style={{ fontSize: 9, color: T.dim, marginBottom: 10 }}>{treasuryPct.toFixed(1)}% of $20M target</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                <div style={{ padding: "6px 8px", background: "#030609", borderRadius: 4, display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 9, color: T.dim }}>Stable reserve</span>
                  <span className={spaceMono.className} style={{ fontSize: 11, color: T.amber }}>${nk(treasuryStable)}</span>
                </div>
                <div style={{ padding: "6px 8px", background: "#030609", borderRadius: 4, display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 9, color: T.dim }}>PAYTKN reserve</span>
                  <span className={spaceMono.className} style={{ fontSize: 11, color: T.cyan }}>{nk(sim?.treasury_paytkn ?? 0)}</span>
                </div>
                <div style={{ padding: "6px 8px", background: "#030609", borderRadius: 4, display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 9, color: T.dim }}>AMM depth</span>
                  <span className={spaceMono.className} style={{ fontSize: 11, color: T.green }}>${nk(sim?.lp_depth ?? 0)}</span>
                </div>
              </div>
            </div>

            {/* Staking */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim, marginBottom: 8 }}>STAKING POOL</div>
              <div className={spaceMono.className} style={{ fontSize: 26, color: T.purple, fontWeight: 700 }}>
                {nk(sim?.staking_pool ?? 0)}
              </div>
              <div style={{ fontSize: 10, color: T.text, marginTop: 1 }}>PAYTKN locked</div>
              <div style={{ marginTop: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 9, color: T.dim }}>Staking ratio</span>
                  <span className={spaceMono.className} style={{ fontSize: 10, color: T.purple }}>
                    {(sim?.staking_ratio_pct ?? ((sim?.staking_pool ?? 0) / Math.max(sim?.total_supply ?? 100e6, 1) * 100)).toFixed(2)}%
                  </span>
                </div>
                <div style={{ height: 4, background: "#030609", borderRadius: 99 }}>
                  <div style={{
                    height: "100%", borderRadius: 99, transition: "width 1.2s ease",
                    width: `${Math.min(100, (sim?.staking_ratio_pct ?? 0) * 3)}%`,
                    background: `linear-gradient(90deg, #6d28d9, ${T.purple})`,
                  }} />
                </div>
              </div>
              <div style={{ marginTop: 8, padding: "6px 8px", background: "#030609", borderRadius: 4, display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 9, color: T.dim }}>Reward pool</span>
                <span className={spaceMono.className} style={{ fontSize: 11, color: T.green }}>
                  {(sim?.reward_pool ?? 0).toFixed(2)} PTK
                </span>
              </div>
            </div>

            {/* Supply */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim, marginBottom: 6 }}>TOTAL SUPPLY</div>
              <div className={spaceMono.className} style={{ fontSize: 22, color: T.cyan, fontWeight: 700 }}>
                {nk(sim?.total_supply ?? 12_000_000)}
              </div>
              <div style={{ fontSize: 10, color: T.text }}>PAYTKN</div>
              <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                <div style={{ padding: "6px 8px", background: "#030609", borderRadius: 4 }}>
                  <div style={{ fontSize: 9, color: T.dim }}>BURNED 🔥</div>
                  <div className={spaceMono.className} style={{ fontSize: 12, color: T.red, marginTop: 1 }}>
                    -{nk(sim?.total_burned ?? 0)}
                  </div>
                </div>
                <div style={{ padding: "6px 8px", background: "#030609", borderRadius: 4 }}>
                  <div style={{ fontSize: 9, color: T.dim }}>MINTED ⛏️</div>
                  <div className={spaceMono.className} style={{ fontSize: 12, color: T.green, marginTop: 1 }}>
                    +{nk(sim?.total_minted ?? 0)}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ── CENTER COLUMN ─────────────────────────────────────────────── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

            {/* Price chart */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim }}>PRICE HISTORY — PAYTKN/USD</div>
                <div className={spaceMono.className} style={{ fontSize: 10, color: T.dim }}>{phData.length} days</div>
              </div>
              <ResponsiveContainer width="100%" height={190}>
                <AreaChart data={phData} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                  <defs>
                    <linearGradient id="pg" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"   stopColor={T.cyan} stopOpacity={0.28} />
                      <stop offset="100%" stopColor={T.cyan} stopOpacity={0}    />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke={T.dimmer} />
                  <XAxis dataKey={phData[0]?.day !== undefined ? "day" : "tick"} tick={false} axisLine={{ stroke: T.border }} />
                  <YAxis domain={["auto","auto"]} tick={{ fill: T.dim, fontSize: 9 }} axisLine={{ stroke: T.border }} tickLine={false} tickFormatter={v => `$${v.toFixed(3)}`} />
                  <Tooltip content={<PriceTip />} />
                  <ReferenceLine y={1.0} stroke={T.dim} strokeDasharray="5 5" label={{ value: "$1.00 peg", fill: T.dim, fontSize: 9, position: "insideTopLeft" }} />
                  <Area type="monotone" dataKey="price" stroke={T.cyan} strokeWidth={1.5} fill="url(#pg)" dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Supply chart */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim }}>CIRCULATING SUPPLY (M PAYTKN)</div>
              </div>
              <ResponsiveContainer width="100%" height={130}>
                <AreaChart data={shData} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                  <defs>
                    <linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"   stopColor={T.purple} stopOpacity={0.22} />
                      <stop offset="100%" stopColor={T.purple} stopOpacity={0}    />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke={T.dimmer} />
                  <XAxis dataKey={shData[0]?.day !== undefined ? "day" : "tick"} tick={false} axisLine={{ stroke: T.border }} />
                  <YAxis tick={{ fill: T.dim, fontSize: 9 }} axisLine={{ stroke: T.border }} tickLine={false} tickFormatter={v => `${v}M`} />
                  <Tooltip contentStyle={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 4 }} labelStyle={{ display: "none" }} formatter={(v: any) => [`${Number(v).toFixed(4)}M PAYTKN`, "Supply"]} />
                  <Area type="monotone" dataKey="supplyM" stroke={T.purple} strokeWidth={1.5} fill="url(#sg)" dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Economy KPIs */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
              <MCard label="VOLUME"       value={usd(sim?.total_volume_usd ?? 0)} />
              <MCard label="PAYMENTS"     value={String(sim?.total_payments ?? 0)} color={T.amber} />
              <MCard label="STAKING RWDS" value={`${nk(sim?.total_staking_rewards ?? 0)} PTK`} color={T.green} />
              <MCard label="TOTAL BURNED" value={`${nk(sim?.total_burned ?? 0)} PTK`} color={T.red} />
            </div>

            {/* Live tx feed */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden" }}>
              <div style={{ padding: "10px 16px 6px", borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 8 }}>
                <LED color={T.green} pulse={running} />
                <span style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim }}>LIVE ACTIVITY FEED</span>
                <span className={spaceMono.className} style={{ marginLeft: "auto", fontSize: 10, color: T.dim }}>
                  {feed.length} events
                </span>
              </div>
              <div style={{ maxHeight: 260, overflowY: "auto" }}>
                {feed.length === 0 ? (
                  <div style={{ padding: "36px", textAlign: "center", color: T.dim, fontSize: 12 }}>
                    {running ? "Generating first events…" : "Start simulation to see live transactions"}
                  </div>
                ) : feed.map((ev, i) => (
                  <div key={`${ev.id}-${i}`} className="sim-feed-row" style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "6px 16px",
                    borderBottom: `1px solid ${T.bg}`,
                    background: i === 0 ? (TX_BG[ev.type] ?? "transparent") : "transparent",
                  }}>
                    <div style={{ width: 2.5, height: 24, borderRadius: 99, background: TX_COLOR[ev.type] ?? T.text, flexShrink: 0 }} />
                    <span className={spaceMono.className} style={{ fontSize: 9, color: T.dim, flexShrink: 0, width: 56 }}>{ev.ts}</span>
                    <span style={{ fontSize: 11.5, color: T.textB, flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {ev.desc}
                    </span>
                    {ev.amount_usd > 0 && (
                      <span className={spaceMono.className} style={{ fontSize: 10, color: T.text, flexShrink: 0 }}>
                        {usd(ev.amount_usd)}
                      </span>
                    )}
                    <span className={spaceMono.className} style={{
                      fontSize: 11, flexShrink: 0, fontWeight: 700, minWidth: 80, textAlign: "right",
                      color: ev.paytkn >= 0 ? (TX_COLOR[ev.type] ?? T.cyan) : T.red,
                    }}>
                      {ev.paytkn >= 0 ? "+" : ""}{ev.paytkn.toFixed(4)} PTK
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── RIGHT COLUMN ──────────────────────────────────────────────── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>

            {/* Population + Sentiment */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim, marginBottom: 10 }}>POPULATION · DAY {simDay}</div>
              {/* Sentiment bar */}
              <div style={{ marginBottom: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 9, color: T.dim }}>Market Sentiment</span>
                  <span className={spaceMono.className} style={{ fontSize: 10, color: sentiment > 0.6 ? T.green : sentiment < 0.4 ? T.red : T.amber, fontWeight: 700 }}>
                    {sentiment > 0.65 ? "BULLISH 🚀" : sentiment < 0.4 ? "BEARISH 📉" : "NEUTRAL 〰️"}
                  </span>
                </div>
                <div style={{ height: 6, background: "#030609", borderRadius: 99, overflow: "hidden" }}>
                  <div style={{
                    height: "100%", borderRadius: 99, transition: "width 1.2s ease",
                    width: `${sentiment * 100}%`,
                    background: sentiment > 0.6 ? `linear-gradient(90deg,#15803d,${T.green})` : sentiment < 0.4 ? `linear-gradient(90deg,#991b1b,${T.red})` : `linear-gradient(90deg,#92400e,${T.amber})`,
                  }} />
                </div>
              </div>
              {/* Archetype breakdown */}
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {Object.entries(archBreak).map(([arch, cnt]) => {
                  const emojiMap: Record<string,string> = { casual:"👤", loyal:"💎", whale:"🐋", speculator:"📈", power_user:"⚡", dormant:"😴" };
                  const colorMap: Record<string,string> = { casual:T.text, loyal:T.cyan, whale:T.purple, speculator:T.orange, power_user:T.green, dormant:T.dim };
                  return (
                    <div key={arch} style={{ display: "flex", alignItems: "center", gap: 7 }}>
                      <span style={{ fontSize: 12, lineHeight: 1, width: 18 }}>{emojiMap[arch] ?? "👤"}</span>
                      <span style={{ fontSize: 9, color: T.dim, flex: 1, textTransform: "capitalize" }}>{arch.replace("_"," ")}</span>
                      <span className={spaceMono.className} style={{ fontSize: 10, color: colorMap[arch] ?? T.text, fontWeight: 700 }}>{cnt}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Top Users */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim }}>TOP USERS</div>
                <div className={spaceMono.className} style={{ fontSize: 9, color: T.dim }}>{sim?.active_users ?? 0} active</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {topUsers.slice(0, 6).map((u) => (
                  <div key={u.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 9px", background: "#030609", borderRadius: 5, border: `1px solid ${T.border}` }}>
                    <span style={{ fontSize: 16, lineHeight: 1, flexShrink: 0 }}>{u.emoji}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ fontSize: 10, color: T.textB, fontWeight: 600, textTransform: "capitalize" }}>{u.archetype.replace("_"," ")}</span>
                        <span style={{ fontSize: 8, color: u.loyalty > 0.8 ? T.green : u.loyalty < 0.6 ? T.red : T.amber }}>{(u.loyalty * 100).toFixed(0)}% loyal</span>
                      </div>
                      <div style={{ display: "flex", gap: 7, marginTop: 2 }}>
                        <span className={spaceMono.className} style={{ fontSize: 9, color: T.cyan }}>{nk(u.wallet)} PTK</span>
                        {u.staked > 0 && <span className={spaceMono.className} style={{ fontSize: 9, color: T.purple }}>{nk(u.staked)} 🔒</span>}
                      </div>
                    </div>
                    <div className={spaceMono.className} style={{ fontSize: 9, color: T.dim, textAlign: "right", flexShrink: 0 }}>{u.txs}tx</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Top Merchants */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim }}>MERCHANT ACTIVITY</div>
                <div className={spaceMono.className} style={{ fontSize: 9, color: T.dim }}>{sim?.active_merchants ?? 0} active</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {topMerchants.slice(0, 5).map((m) => (
                  <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 9px", background: "#030609", borderRadius: 5 }}>
                    <span style={{ fontSize: 14, lineHeight: 1 }}>{m.emoji}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 10, color: T.textB, fontWeight: 600 }}>{m.name}</div>
                      <div className={spaceMono.className} style={{ fontSize: 8, color: T.dim }}>{m.tx_count} orders · {m.archetype.replace("_"," ")}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div className={spaceMono.className} style={{ fontSize: 11, color: T.green, fontWeight: 700 }}>{nk(m.volume)}</div>
                      {m.loan_balance > 0 && <div className={spaceMono.className} style={{ fontSize: 8, color: T.red }}>loan:{nk(m.loan_balance)}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* RL Agent parameters */}
            <div style={{ background: T.panel, border: `1px solid rgba(168,85,247,0.25)`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
                <LED color={T.purple} pulse={running} />
                <div style={{ fontSize: 9, letterSpacing: "0.14em", color: "#6d28d9" }}>PPO AGENT · LIVE PARAMS</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {Object.entries(params).filter(([k]) => !PARAM_SKIP.has(k)).map(([k, v]) => {
                  const pct = ((v as number) / (PARAM_MAX[k] ?? 100)) * 100;
                  return (
                    <div key={k}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontSize: 9, color: T.dim, letterSpacing: "0.04em" }}>{PARAM_LABEL[k] ?? k}</span>
                        <span className={spaceMono.className} style={{ fontSize: 10, color: T.purple, fontWeight: 700 }}>{String(v)}</span>
                      </div>
                      <div style={{ height: 3, background: "#030609", borderRadius: 99 }}>
                        <div style={{
                          height: "100%", width: `${pct}%`, borderRadius: 99,
                          background: `linear-gradient(90deg, #5b21b6, ${T.purple})`,
                          transition: "width 1.2s ease",
                          boxShadow: `0 0 4px ${T.purple}44`,
                        }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              <div style={{ marginTop: 12, fontSize: 9, color: T.dimmer, textAlign: "center" }}>
                Updated by PPO model every 30s · 1 day per tick
              </div>
            </div>

            {/* System health */}
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ fontSize: 9, letterSpacing: "0.14em", color: T.dim, marginBottom: 10 }}>SYSTEM HEALTH</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {[
                  { label: "Backend API",    ok: backOk,   port: "8000" },
                  { label: "RL Model Server",ok: running,  port: "8001" },
                  { label: "Simulation",     ok: running,  port: "active" },
                  { label: "Base Sepolia",   ok: true,     port: "testnet" },
                ].map(s => (
                  <div key={s.label} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                      <LED color={s.ok ? T.green : T.red} pulse={s.ok} />
                      <span style={{ fontSize: 11, color: T.text }}>{s.label}</span>
                    </div>
                    <span className={spaceMono.className} style={{ fontSize: 9, color: T.dim }}>{s.port}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ══ AI DECISION LOG ═════════════════════════════════════════════════ */}
        <div style={{ padding: "0 20px 28px" }}>
          <div style={{ background: T.panel, border: `1px solid rgba(168,85,247,0.35)`, borderRadius: 8, overflow: "hidden" }}>

            {/* Section header */}
            <div style={{
              padding: "12px 20px", borderBottom: `1px solid ${T.border}`,
              display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
            }}>
              <LED color={T.purple} pulse={running} />
              <span className={orbitron.className} style={{ fontSize: 10, letterSpacing: "0.18em", color: "#9333ea", fontWeight: 700 }}>
                AI DECISION LOG
              </span>
              <span style={{ fontSize: 10, color: T.dim }}>— what the RL agent changed &amp; why</span>
              <div style={{ marginLeft: "auto", display: "flex", align: "center", gap: 12 }}>
                {decisions.length > 0 && (
                  <span className={spaceMono.className} style={{ fontSize: 9, color: T.purple }}>
                    {decisions.length} decision{decisions.length !== 1 ? "s" : ""} recorded
                  </span>
                )}
                <span className={spaceMono.className} style={{ fontSize: 9, color: T.dim }}>
                  PPO updates every ~30s · tracking {Object.keys(params).filter(k => !PARAM_SKIP.has(k)).length} parameters
                </span>
              </div>
            </div>

            {/* Empty state */}
            {decisions.length === 0 && (
              <div style={{ padding: "48px 20px", textAlign: "center" }}>
                <div style={{ fontSize: 32, marginBottom: 12 }}>🤖</div>
                <div style={{ fontSize: 13, color: T.text, marginBottom: 6 }}>
                  {running ? "Watching for parameter changes…" : "Start the simulation to see AI decisions"}
                </div>
                <div style={{ fontSize: 10, color: T.dim }}>
                  Entries appear whenever the PPO agent adjusts burn rate, cashback, staking rewards, or other economic levers
                </div>
              </div>
            )}

            {/* Decision cards grid */}
            {decisions.length > 0 && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
                {decisions.map((d, i) => {
                  const pct = Math.abs(((d.newVal - d.oldVal) / Math.max(d.oldVal, 1)) * 100);
                  const isUp = d.direction === "up";
                  const accentColor = isUp ? T.green : T.red;
                  return (
                    <div key={d.id} style={{
                      padding: "16px 20px",
                      borderBottom: `1px solid ${T.bg}`,
                      borderRight: `1px solid ${T.bg}`,
                      background: i === 0 ? `rgba(168,85,247,0.04)` : "#030609",
                      animation: i === 0 ? "row-in 0.4s ease" : undefined,
                    }}>

                      {/* Top row: icon + action + day */}
                      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 10 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span style={{ fontSize: 22, lineHeight: 1 }}>{d.icon}</span>
                          <div>
                            <div style={{ fontSize: 12, color: T.textB, fontWeight: 700, lineHeight: 1.2 }}>{d.action}</div>
                            <div style={{ fontSize: 9, color: T.dim, marginTop: 3, letterSpacing: "0.06em" }}>
                              {PARAM_LABEL[d.param] ?? d.param}
                            </div>
                          </div>
                        </div>
                        <div style={{ textAlign: "right", flexShrink: 0 }}>
                          <div className={spaceMono.className} style={{ fontSize: 10, color: T.cyan }}>Day {d.day}</div>
                          <div className={spaceMono.className} style={{ fontSize: 9, color: T.dim }}>{d.ts}</div>
                        </div>
                      </div>

                      {/* Value change bar */}
                      <div style={{
                        display: "flex", alignItems: "center", gap: 10,
                        background: T.bg, borderRadius: 6, padding: "8px 12px", marginBottom: 10,
                      }}>
                        <span className={spaceMono.className} style={{ fontSize: 13, color: T.dim }}>{d.oldVal}</span>
                        <div style={{ flex: 1, height: 3, background: "#0d1f38", borderRadius: 99, overflow: "hidden" }}>
                          <div style={{
                            height: "100%", borderRadius: 99,
                            width: `${Math.min(100, pct * 3)}%`,
                            background: `linear-gradient(90deg, ${accentColor}66, ${accentColor})`,
                            transition: "width 0.8s ease",
                          }} />
                        </div>
                        <span className={spaceMono.className} style={{ fontSize: 15, fontWeight: 700, color: accentColor }}>{d.newVal}</span>
                        <span style={{ fontSize: 11, color: accentColor, fontWeight: 700 }}>
                          {isUp ? "▲" : "▼"} {pct.toFixed(1)}%
                        </span>
                      </div>

                      {/* Reason */}
                      <div style={{
                        fontSize: 11, color: T.text, lineHeight: 1.6,
                        padding: "9px 12px",
                        background: "rgba(168,85,247,0.05)",
                        border: "1px solid rgba(168,85,247,0.12)",
                        borderRadius: 6,
                      }}>
                        <span style={{ color: T.purple, marginRight: 6, fontSize: 12 }}>🤖</span>
                        {d.reason}
                      </div>

                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
