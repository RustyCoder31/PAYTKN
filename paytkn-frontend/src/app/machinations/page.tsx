"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { Orbitron, Space_Mono } from "next/font/google";
import { api } from "@/lib/api";

const orbitron  = Orbitron({ subsets: ["latin"], weight: ["700", "900"] });
const spaceMono = Space_Mono({ subsets: ["latin"], weight: ["400", "700"] });

const T = {
  bg: "#010408", panel: "#050a10", border: "#0c1a2e",
  cyan: "#06b6d4", green: "#22c55e", red: "#ef4444",
  purple: "#a855f7", amber: "#f59e0b", orange: "#fb923c",
  text: "#94a3b8", dim: "#1e3252", textB: "#e2e8f0",
};

const nk = (v: number) =>
  v >= 1e9 ? `${(v/1e9).toFixed(2)}B`
  : v >= 1e6 ? `${(v/1e6).toFixed(2)}M`
  : v >= 1e3 ? `${(v/1e3).toFixed(1)}k`
  : (v ?? 0).toFixed(1);

// ─── Node layout ────────────────────────────────────────────────────────────
// viewBox: 0 0 1320 640

const NODES = {
  users:       { x: 110, y: 300, w: 140, h: 90,  color: T.cyan,   label: "USERS",        icon: "👥" },
  merchants:   { x: 1070,y: 300, w: 140, h: 90,  color: T.orange, label: "MERCHANTS",    icon: "🏪" },
  staking:     { x: 380, y:  80, w: 145, h: 80,  color: T.purple, label: "STAKING POOL", icon: "🔒" },
  rewards:     { x: 795, y:  80, w: 145, h: 80,  color: T.green,  label: "REWARD POOL",  icon: "🏆" },
  rl_agent:    { x: 565, y: 255, w: 150, h: 90,  color: "#c084fc",label: "RL AGENT",     icon: "🤖" },
  amm:         { x: 320, y: 480, w: 145, h: 80,  color: T.cyan,   label: "AMM POOL",     icon: "⚡" },
  treasury:    { x: 575, y: 480, w: 150, h: 80,  color: T.amber,  label: "TREASURY",     icon: "💰" },
  burn:        { x: 840, y: 480, w: 130, h: 80,  color: T.red,    label: "BURN SINK",    icon: "🔥" },
};

// Flow path definitions (SVG path data)  cx = x + w/2, cy = y + h/2
const cx = (k: keyof typeof NODES) => NODES[k].x + NODES[k].w / 2;
const cy = (k: keyof typeof NODES) => NODES[k].y + NODES[k].h / 2;

// Returns edge path between two nodes (exits from/enters to nearest edges)
function bezier(x1:number,y1:number,x2:number,y2:number, cx1?:number,cy1?:number,cx2?:number,cy2?:number): string {
  const mx = (x1+x2)/2, my = (y1+y2)/2;
  const c1x = cx1 ?? (x1*0.4 + x2*0.6); const c1y = cy1 ?? my;
  const c2x = cx2 ?? (x1*0.6 + x2*0.4); const c2y = cy2 ?? my;
  return `M ${x1} ${y1} C ${c1x} ${c1y} ${c2x} ${c2y} ${x2} ${y2}`;
}

interface FlowDef {
  id: string; path: string; color: string;
  label: string; particles: number; speed: number;
  labelPos: [number, number];
  arrow?: boolean;
}

const FLOWS: FlowDef[] = [
  // Users → Merchants (payments) — big arc over the top
  {
    id: "pay",
    path: `M ${cx("users")+65} ${cy("users")-20} C 400 140 880 140 ${cx("merchants")-65} ${cy("merchants")-20}`,
    color: T.cyan, label: "PAYMENTS", particles: 5, speed: 3.2,
    labelPos: [660, 118],
  },
  // Users → Staking Pool (stake)
  {
    id: "stake_u",
    path: bezier(cx("users")+20, NODES["users"].y, cx("staking"), cy("staking")+35, 220, 150, 390, 160),
    color: T.purple, label: "STAKE", particles: 3, speed: 2.8,
    labelPos: [245, 155],
  },
  // Reward Pool → Users (distribute)
  {
    id: "dist",
    path: `M ${cx("rewards")} ${cy("rewards")+35} C 780 220 350 350 ${cx("users")+60} ${NODES["users"].y}`,
    color: T.green, label: "REWARDS", particles: 3, speed: 4.0,
    labelPos: [390, 260],
  },
  // Staking Pool ↔ Reward Pool
  {
    id: "s_to_r",
    path: `M ${cx("staking")+72} ${cy("staking")} L ${cx("rewards")-72} ${cy("rewards")}`,
    color: T.purple, label: "EPOCH DIST", particles: 2, speed: 3.5,
    labelPos: [590, 112],
  },
  // Merchants → Staking (auto-stake)
  {
    id: "stake_m",
    path: bezier(cx("merchants")-20, NODES["merchants"].y, cx("staking")+72, cy("staking"), 960, 180, 750, 90),
    color: "#9333ea", label: "AUTO-STAKE", particles: 2, speed: 3.0,
    labelPos: [890, 138],
  },
  // Payment fees → Treasury
  {
    id: "fee_treas",
    path: `M 660 ${cy("rl_agent")+42} C 660 390 640 430 ${cx("treasury")} ${NODES["treasury"].y}`,
    color: T.amber, label: "TREASURY FEE", particles: 2, speed: 2.5,
    labelPos: [683, 420],
  },
  // Payment fees → Burn
  {
    id: "fee_burn",
    path: `M 710 ${cy("rl_agent")+42} C 780 390 830 440 ${cx("burn")} ${NODES["burn"].y}`,
    color: T.red, label: "BURN", particles: 2, speed: 2.2,
    labelPos: [800, 438],
  },
  // Payment fees → Reward Pool
  {
    id: "fee_reward",
    path: `M 610 ${NODES["rl_agent"].y} C 650 180 760 120 ${cx("rewards")} ${cy("rewards")+35}`,
    color: T.green, label: "REWARD ALLOC", particles: 2, speed: 3.0,
    labelPos: [715, 198],
  },
  // Users → AMM (DEX buy)
  {
    id: "dex_buy",
    path: bezier(cx("users")+10, NODES["users"].y+NODES["users"].h, cx("amm")-20, cy("amm"), 130, 480, 290, 490),
    color: "#22d3ee", label: "DEX BUY", particles: 2, speed: 2.5,
    labelPos: [200, 500],
  },
  // AMM → Users (DEX sell)
  {
    id: "dex_sell",
    path: bezier(cx("amm")-20, cy("amm"), cx("users")+10, NODES["users"].y+NODES["users"].h, 280, 540, 130, 520),
    color: T.orange, label: "DEX SELL", particles: 1, speed: 3.5,
    labelPos: [195, 540],
  },
  // AMM ↔ Treasury (rebalance)
  {
    id: "amm_treas",
    path: `M ${cx("amm")+72} ${cy("amm")} L ${cx("treasury")-75} ${cy("treasury")}`,
    color: T.amber, label: "REBALANCE", particles: 2, speed: 4.0,
    labelPos: [490, 548],
  },
  // RL Agent → all (params) — dashed lines to corners
  {
    id: "rl_users",
    path: `M ${cx("rl_agent")-70} ${cy("rl_agent")} C 350 300 280 290 ${cx("users")+65} ${cy("users")}`,
    color: "#c084fc", label: "", particles: 1, speed: 2.0,
    labelPos: [300, 295],
  },
  {
    id: "rl_merch",
    path: `M ${cx("rl_agent")+75} ${cy("rl_agent")} C 880 290 960 295 ${cx("merchants")-65} ${cy("merchants")}`,
    color: "#c084fc", label: "", particles: 1, speed: 2.2,
    labelPos: [870, 287],
  },
];

// ─── Particle component ──────────────────────────────────────────────────────
function FlowParticles({ flow }: { flow: FlowDef }) {
  const count = flow.particles;
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <circle key={i} r={2.5} fill={flow.color} opacity={0.85}>
          <animateMotion
            dur={`${flow.speed}s`}
            begin={`${(i / count) * flow.speed}s`}
            repeatCount="indefinite"
            path={flow.path}
          />
        </circle>
      ))}
    </>
  );
}

// ─── Node box ────────────────────────────────────────────────────────────────
function MachNode({
  node, value1, label1, value2, label2, glow = false,
}: {
  node: keyof typeof NODES;
  value1: string; label1: string;
  value2?: string; label2?: string;
  glow?: boolean;
}) {
  const n = NODES[node];
  return (
    <g>
      {/* Glow rectangle */}
      {glow && (
        <rect x={n.x - 3} y={n.y - 3} width={n.w + 6} height={n.h + 6}
          rx={10} ry={10} fill="none" stroke={n.color} strokeWidth={1}
          opacity={0.3}
          style={{ filter: `blur(4px)` }}
        />
      )}
      {/* Main box */}
      <rect x={n.x} y={n.y} width={n.w} height={n.h}
        rx={8} ry={8}
        fill="#05090f" stroke={n.color} strokeWidth={1.5}
        style={{ filter: glow ? `drop-shadow(0 0 6px ${n.color}66)` : "none" }}
      />
      {/* Header bar */}
      <rect x={n.x} y={n.y} width={n.w} height={22} rx={8} ry={8} fill={`${n.color}22`} />
      <rect x={n.x} y={n.y + 14} width={n.w} height={8} fill={`${n.color}22`} />
      {/* Icon + label */}
      <text x={n.x + 10} y={n.y + 15} fontSize={10} fill={n.color}
        style={{ fontFamily: "'Orbitron', monospace", letterSpacing: "0.08em", fontWeight: 700 }}>
        {n.icon} {n.label}
      </text>
      {/* Value 1 */}
      <text x={n.x + 8} y={n.y + 42} fontSize={15} fontWeight={700} fill={n.color}
        style={{ fontFamily: "'Space Mono', monospace" }}>
        {value1}
      </text>
      <text x={n.x + 8} y={n.y + 57} fontSize={9} fill={T.text}
        style={{ fontFamily: "'Space Mono', monospace" }}>
        {label1}
      </text>
      {/* Value 2 (optional) */}
      {value2 && (
        <>
          <text x={n.x + 8} y={n.y + 73} fontSize={11} fontWeight={700} fill={`${n.color}bb`}
            style={{ fontFamily: "'Space Mono', monospace" }}>
            {value2}
          </text>
          <text x={n.x + 8} y={n.y + 84} fontSize={8} fill={T.dim}
            style={{ fontFamily: "'Space Mono', monospace" }}>
            {label2}
          </text>
        </>
      )}
    </g>
  );
}

// ─── Flow arrow ──────────────────────────────────────────────────────────────
function FlowArrow({ flow, rate }: { flow: FlowDef; rate?: string }) {
  return (
    <g>
      {/* Path line */}
      <path d={flow.path} fill="none" stroke={flow.color}
        strokeWidth={flow.id === "pay" ? 2 : 1.5}
        strokeOpacity={flow.id.startsWith("rl_") ? 0.4 : 0.55}
        strokeDasharray={flow.id.startsWith("rl_") ? "4 4" : undefined}
      />
      {/* Particles */}
      <FlowParticles flow={flow} />
      {/* Label */}
      {flow.label && (
        <text
          x={flow.labelPos[0]} y={flow.labelPos[1]}
          fontSize={8} fill={flow.color} opacity={0.8}
          textAnchor="middle"
          style={{ fontFamily: "'Space Mono', monospace", letterSpacing: "0.05em" }}
        >
          {flow.label}{rate ? ` ${rate}` : ""}
        </text>
      )}
    </g>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function MachinationsPage() {
  const [sim, setSim]     = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [backOk, setBackOk]   = useState(true);

  const load = useCallback(async () => {
    try {
      const s = await api.simState();
      setSim(s); setRunning(s.running); setBackOk(true);
    } catch { setBackOk(false); }
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const s = await api.simState();
        if (mounted && !s.running) await api.simStart();
        if (mounted) { setSim(s); setRunning(true); }
      } catch {}
    })();
    const t = setInterval(() => { if (mounted) load(); }, 2500);
    return () => { mounted = false; clearInterval(t); };
  }, [load]);

  const price      = sim?.token_price_usd ?? 1.0;
  const supply     = sim?.total_supply     ?? 100_000_000;
  const staked     = sim?.staking_pool     ?? 0;
  const rewPool    = sim?.reward_pool      ?? 0;
  const tStable    = sim?.treasury_stable  ?? (sim?.treasury_eth != null ? sim.treasury_eth * 3100 : 0);
  const tPaytkn    = sim?.treasury_paytkn  ?? 0;
  const tValue     = sim?.treasury_value_usd ?? (tStable + tPaytkn * price);
  const lpD        = sim?.lp_depth         ?? 0;
  const lpPtk      = sim?.lp_paytkn        ?? 0;
  const burned     = sim?.total_burned     ?? 0;
  const activeU    = sim?.active_users     ?? Object.values(sim?.users ?? {}).length;
  const totalU     = sim?.total_users      ?? activeU;
  const activeM    = sim?.active_merchants ?? Object.keys(sim?.merchants ?? {}).length;
  const apy        = sim?.current_apy_pct  ?? 12;
  const sentiment  = sim?.sentiment        ?? 0.5;
  const payments   = sim?.total_payments   ?? 0;
  const volume     = sim?.total_volume_usd ?? 0;
  const day        = sim?.day ?? sim?.tick ?? 0;
  const cashback   = sim?.total_cashback   ?? 0;
  const stakingR   = sim?.staking_ratio_pct ?? (staked / Math.max(supply, 1) * 100);
  const volatility = sim?.price_volatility ?? 0;
  const mcap       = sim?.market_cap       ?? supply * price;

  // Top merchant volume
  const topMerch   = (sim?.top_merchants ?? Object.values(sim?.merchants ?? {}));
  const merchantVol = topMerch.reduce((a: number, m: any) => a + (m.volume ?? m.total_received ?? 0), 0);

  // Flow rates (per day derived from totals)
  const dayRate = Math.max(day, 1);
  const payRate  = `$${nk(volume / dayRate)}/d`;
  const burnRate = `${nk(burned / dayRate)}/d`;
  const rewRate  = `${nk((sim?.total_staking_rewards ?? 0) / dayRate)}/d`;

  return (
    <div style={{ background: T.bg, minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <style>{`
        @keyframes led-pulse { 0%,100%{opacity:1} 50%{opacity:0.25} }
        ::-webkit-scrollbar { width: 3px; }
        ::-webkit-scrollbar-track { background: ${T.bg}; }
        ::-webkit-scrollbar-thumb { background: ${T.border}; }
      `}</style>

      {/* ─ HEADER ──────────────────────────────────────────────────── */}
      <div style={{
        background: "rgba(5,9,15,0.97)", borderBottom: `1px solid ${T.border}`,
        backdropFilter: "blur(12px)", padding: "10px 24px",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div className={orbitron.className} style={{ fontSize: 13, letterSpacing: "0.2em", color: T.cyan, fontWeight: 900 }}>
            PAYTKN · TOKEN FLOW MACHINATIONS
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {[
              { l: "DAY",       v: String(day),                            c: T.cyan   },
              { l: "PRICE",     v: `$${price.toFixed(4)}`,                 c: price > 1 ? T.green : T.red },
              { l: "VOLUME",    v: `$${nk(volume)}`,                       c: T.amber  },
              { l: "PAYMENTS",  v: String(payments),                       c: T.orange },
              { l: "SENTIMENT", v: sentiment > 0.6 ? "BULL" : sentiment < 0.4 ? "BEAR" : "NEUTRAL", c: sentiment > 0.6 ? T.green : sentiment < 0.4 ? T.red : T.amber },
            ].map(b => (
              <div key={b.l} style={{ padding: "3px 10px", border: `1px solid ${T.border}`, borderRadius: 4, background: T.panel, display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 8, color: T.dim, letterSpacing: "0.12em" }}>{b.l}</span>
                <span className={spaceMono.className} style={{ fontSize: 12, fontWeight: 700, color: b.c }}>{b.v}</span>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{
              display: "inline-block", width: 7, height: 7, borderRadius: "50%",
              background: running ? T.green : T.red,
              boxShadow: running ? `0 0 6px ${T.green}` : "none",
              animation: running ? "led-pulse 1.4s infinite" : "none",
            }} />
            <span style={{ fontSize: 10, color: running ? T.green : T.red, letterSpacing: "0.14em", fontWeight: 700 }}>
              {running ? "LIVE" : "PAUSED"}
            </span>
            {!backOk && <span style={{ fontSize: 9, color: T.red, marginLeft: 4 }}>⚠ OFFLINE</span>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {[
            { l: running ? "⏹ STOP" : "▶ START", fn: async () => { try { running ? await api.simStop() : await api.simStart(); setRunning(!running); } catch {} }, c: running ? T.red : T.green },
            { l: "↺ RESET", fn: async () => { try { await api.simReset(); setSim(null); setRunning(false); } catch {} }, c: T.amber },
          ].map(b => (
            <button key={b.l} onClick={b.fn} style={{
              padding: "6px 16px", borderRadius: 5, fontSize: 11, fontWeight: 700,
              background: `${b.c}18`, border: `1px solid ${b.c}55`, color: b.c,
              cursor: "pointer", letterSpacing: "0.07em", fontFamily: "inherit",
            }}>{b.l}</button>
          ))}
        </div>
      </div>

      {/* ─ MAIN CONTENT ─────────────────────────────────────────────── */}
      <div style={{ flex: 1, padding: "12px 16px", display: "flex", gap: 14 }}>

        {/* ─ DIAGRAM ─────────────────────────────────────────────────── */}
        <div style={{
          flex: 1, background: T.panel, border: `1px solid ${T.border}`,
          borderRadius: 10, overflow: "hidden", position: "relative",
        }}>
          {/* Subtle dot grid */}
          <div style={{
            position: "absolute", inset: 0, pointerEvents: "none",
            backgroundImage: `radial-gradient(${T.border} 1px, transparent 1px)`,
            backgroundSize: "28px 28px", opacity: 0.5,
          }} />

          <svg
            viewBox="0 0 1320 640"
            style={{ width: "100%", height: "100%", display: "block" }}
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* ── Background section labels ─────────────────── */}
            <text x={640} y={26} textAnchor="middle" fontSize={9} fill={T.dim}
              style={{ fontFamily: "'Orbitron',monospace", letterSpacing: "0.15em" }}>
              ◆ STAKING LAYER ◆
            </text>
            <text x={640} y={620} textAnchor="middle" fontSize={9} fill={T.dim}
              style={{ fontFamily: "'Orbitron',monospace", letterSpacing: "0.15em" }}>
              ◆ LIQUIDITY LAYER ◆
            </text>
            <text x={30} y={310} textAnchor="middle" fontSize={9} fill={T.dim}
              transform="rotate(-90, 30, 310)"
              style={{ fontFamily: "'Orbitron',monospace", letterSpacing: "0.15em" }}>
              USERS
            </text>
            <text x={1290} y={310} textAnchor="middle" fontSize={9} fill={T.dim}
              transform="rotate(90, 1290, 310)"
              style={{ fontFamily: "'Orbitron',monospace", letterSpacing: "0.15em" }}>
              MERCHANTS
            </text>

            {/* ── Section dividers (faint) ─────────────────── */}
            <line x1={60} y1={200} x2={1260} y2={200} stroke={T.border} strokeWidth={0.5} strokeDasharray="6 8" />
            <line x1={60} y1={440} x2={1260} y2={440} stroke={T.border} strokeWidth={0.5} strokeDasharray="6 8" />

            {/* ── Flow paths (behind nodes) ─────────────────── */}
            {FLOWS.map(f => (
              <FlowArrow key={f.id} flow={f}
                rate={f.id === "pay" ? payRate : f.id === "fee_burn" ? burnRate : f.id === "dist" ? rewRate : undefined}
              />
            ))}

            {/* ── Nodes ────────────────────────────────────── */}
            <MachNode node="users"
              value1={`${activeU} / ${totalU}`}
              label1="active / total"
              value2={`$${nk(volume)}`}
              label2="lifetime volume"
              glow={running}
            />
            <MachNode node="merchants"
              value1={`${activeM}`}
              label1="active merchants"
              value2={`${nk(merchantVol)} PTK`}
              label2="total revenue"
              glow={running}
            />
            <MachNode node="staking"
              value1={`${nk(staked)}`}
              label1="PAYTKN locked"
              value2={`${stakingR.toFixed(1)}% ratio`}
              label2={`APY ${apy.toFixed(1)}%`}
              glow={running}
            />
            <MachNode node="rewards"
              value1={`${nk(rewPool)}`}
              label1="reward pool (PTK)"
              value2={`${nk(sim?.total_staking_rewards ?? 0)}`}
              label2="total distributed"
              glow={running}
            />
            <MachNode node="rl_agent"
              value1={`Day ${day}`}
              label1="PPO v4 · controlling"
              value2={`${(volatility * 100).toFixed(3)}% vol`}
              label2={`sentiment ${(sentiment * 100).toFixed(0)}%`}
              glow={running}
            />
            <MachNode node="amm"
              value1={`${nk(lpPtk)}`}
              label1="PAYTKN reserves"
              value2={`$${nk(lpD / 2)}`}
              label2="stable reserves"
              glow={false}
            />
            <MachNode node="treasury"
              value1={`$${nk(tValue)}`}
              label1="total value"
              value2={`${nk(tPaytkn)} + $${nk(tStable)}`}
              label2="PTK + stable"
              glow={false}
            />
            <MachNode node="burn"
              value1={`${nk(burned)}`}
              label1="total burned (PTK)"
              value2={`-${burnRate}`}
              label2="burn rate"
              glow={false}
            />

            {/* ── Price peg indicator — sits in the gap between RL Agent (y≤345)
                   and the bottom layer (y≥480), centred horizontally ────── */}
            <g transform="translate(640, 400)">
              {/* Outer ring glow */}
              <circle r={42} fill="none"
                stroke={price > 1.02 ? T.green : price < 0.98 ? T.red : T.amber}
                strokeWidth={0.5} opacity={0.2}
              />
              <circle r={36} fill="#05090f"
                stroke={price > 1.02 ? T.green : price < 0.98 ? T.red : T.amber}
                strokeWidth={1.5}
                style={{ filter: `drop-shadow(0 0 10px ${price > 1.02 ? T.green : price < 0.98 ? T.red : T.amber}55)` }}
              />
              <text textAnchor="middle" y={-7} fontSize={11} fontWeight={700}
                fill={price > 1.02 ? T.green : price < 0.98 ? T.red : T.amber}
                style={{ fontFamily: "'Space Mono',monospace" }}>
                ${price.toFixed(4)}
              </text>
              <text textAnchor="middle" y={8} fontSize={7.5} fill={T.text}
                style={{ fontFamily: "'Space Mono',monospace" }}>
                AMM PRICE
              </text>
              <text textAnchor="middle" y={22} fontSize={7} fill={T.dim}
                style={{ fontFamily: "'Space Mono',monospace" }}>
                peg $1.00
              </text>
            </g>

            {/* ── RL Agent params ──────────────────────────── */}
            {sim?.rl_params && (() => {
              const p = sim.rl_params;
              const lines = [
                `burn:${p.burn_rate_bps}bps`,
                `cashback:${p.cashback_base_bps}bps`,
                `reward:${p.reward_alloc_bps}bps`,
              ];
              return lines.map((line, i) => (
                <text key={i} x={cx("rl_agent")} y={NODES["rl_agent"].y - 12 - (lines.length - 1 - i) * 12}
                  textAnchor="middle" fontSize={8} fill="#c084fc" opacity={0.6}
                  style={{ fontFamily: "'Space Mono',monospace" }}>
                  {line}
                </text>
              ));
            })()}

            {/* ── Market cap label ─────────────────────────── */}
            <text x={640} y={635} textAnchor="middle" fontSize={9} fill={T.dim}
              style={{ fontFamily: "'Space Mono',monospace" }}>
              Market Cap: ${nk(mcap)} · Supply: {nk(supply)} PTK · Cashback distributed: {nk(cashback)} PTK
            </text>
          </svg>
        </div>

        {/* ─ RIGHT PANEL ─────────────────────────────────────────────── */}
        <div style={{ width: 200, display: "flex", flexDirection: "column", gap: 10 }}>

          {/* Flow legend */}
          <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "12px 14px" }}>
            <div className={orbitron.className} style={{ fontSize: 8, letterSpacing: "0.14em", color: T.dim, marginBottom: 10 }}>FLOW LEGEND</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {[
                { color: T.cyan,    label: "Payments",     desc: "User → Merchant" },
                { color: T.purple,  label: "Staking",      desc: "Lock PAYTKN" },
                { color: T.green,   label: "Rewards",      desc: "Pool → Stakers" },
                { color: T.red,     label: "Burn",         desc: "Destroyed" },
                { color: T.amber,   label: "Treasury",     desc: "Fee routing" },
                { color: "#22d3ee", label: "DEX Buy",      desc: "PAYTKN demand" },
                { color: T.orange,  label: "DEX Sell",     desc: "Exit pressure" },
                { color: "#c084fc", label: "RL Agent",     desc: "Param control" },
              ].map(f => (
                <div key={f.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <svg width={24} height={8}>
                    <line x1={0} y1={4} x2={16} y2={4} stroke={f.color} strokeWidth={1.5} />
                    <circle cx={20} cy={4} r={2.5} fill={f.color} opacity={0.9} />
                  </svg>
                  <div>
                    <div className={spaceMono.className} style={{ fontSize: 9, color: f.color, fontWeight: 700 }}>{f.label}</div>
                    <div style={{ fontSize: 8, color: T.dim }}>{f.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Economy health */}
          <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "12px 14px" }}>
            <div className={orbitron.className} style={{ fontSize: 8, letterSpacing: "0.14em", color: T.dim, marginBottom: 10 }}>ECONOMY HEALTH</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { label: "Price Stability", value: Math.max(0, 100 - volatility * 10000), color: T.green },
                { label: "Staking Ratio",   value: Math.min(100, stakingR * 3),           color: T.purple },
                { label: "Treasury Health", value: Math.min(100, tValue / 200_000),       color: T.amber },
                { label: "User Sentiment",  value: sentiment * 100,                        color: T.cyan },
              ].map(({ label, value, color }) => (
                <div key={label}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                    <span style={{ fontSize: 8, color: T.dim }}>{label}</span>
                    <span className={spaceMono.className} style={{ fontSize: 9, color, fontWeight: 700 }}>{value.toFixed(0)}%</span>
                  </div>
                  <div style={{ height: 4, background: "#030609", borderRadius: 99 }}>
                    <div style={{
                      height: "100%", width: `${Math.min(100, Math.max(0, value))}%`, borderRadius: 99,
                      background: color, transition: "width 1.5s ease",
                      boxShadow: `0 0 4px ${color}55`,
                    }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Daily snapshot */}
          <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "12px 14px" }}>
            <div className={orbitron.className} style={{ fontSize: 8, letterSpacing: "0.14em", color: T.dim, marginBottom: 10 }}>
              DAY {day} SNAPSHOT
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {[
                { l: "Payments/day",   v: `${(payments/dayRate).toFixed(0)}` },
                { l: "Vol/day",        v: `$${nk(volume/dayRate)}` },
                { l: "Burn/day",       v: `${nk(burned/dayRate)} PTK` },
                { l: "Rewards/day",    v: `${nk((sim?.total_staking_rewards??0)/dayRate)} PTK` },
                { l: "Active users",   v: `${activeU}` },
                { l: "Cashback given", v: `${nk(cashback)} PTK` },
              ].map(({ l, v }) => (
                <div key={l} style={{ display: "flex", justifyContent: "space-between", borderBottom: `1px solid ${T.border}`, paddingBottom: 4 }}>
                  <span style={{ fontSize: 8, color: T.dim }}>{l}</span>
                  <span className={spaceMono.className} style={{ fontSize: 10, color: T.textB, fontWeight: 700 }}>{v}</span>
                </div>
              ))}
            </div>
          </div>

          {/* RL params */}
          <div style={{ background: T.panel, border: `1px solid rgba(168,85,247,0.3)`, borderRadius: 8, padding: "12px 14px" }}>
            <div className={orbitron.className} style={{ fontSize: 8, letterSpacing: "0.14em", color: "#9333ea", marginBottom: 10 }}>
              🤖 RL AGENT PARAMS
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {Object.entries(sim?.rl_params ?? {
                burn_rate_bps: 20, cashback_base_bps: 50,
                reward_alloc_bps: 3000, treasury_ratio_bps: 6000,
              }).map(([k, v]) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 8, color: T.dim }}>{k.replace(/_/g,' ')}</span>
                  <span className={spaceMono.className} style={{ fontSize: 9, color: "#c084fc", fontWeight: 700 }}>{String(v)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
