"use client";
import { useEffect, useState, useCallback } from "react";
import { StatCard } from "@/components/StatCard";
import { api, modelApi } from "@/lib/api";
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip } from "recharts";

interface Params {
  mint_factor:        number;
  burn_rate_bps:      number;
  reward_alloc_bps:   number;
  cashback_base_bps:  number;
  merchant_alloc_bps: number;
  treasury_ratio_bps: number;
}

const PARAM_META: Record<keyof Params, { label: string; min: number; max: number; unit: string; desc: string }> = {
  mint_factor:        { label: "Mint Factor",      min: 1,    max: 200,  unit: "×/100",   desc: "New token minting rate. Agent increases when demand > supply." },
  burn_rate_bps:      { label: "Burn Rate",         min: 0,    max: 5,    unit: "bps/day", desc: "Daily deflationary burn on circulating supply." },
  reward_alloc_bps:   { label: "Staking Reward %",  min: 1000, max: 6000, unit: "bps",     desc: "% of protocol fees flowing to the staking reward pool." },
  cashback_base_bps:  { label: "Cashback Base",     min: 10,   max: 100,  unit: "bps",     desc: "Base cashback rate. Multiplied per-user by staking/loyalty/invites." },
  merchant_alloc_bps: { label: "Merchant Alloc %",  min: 100,  max: 2500, unit: "bps",     desc: "% of fees routed to the merchant staking pool." },
  treasury_ratio_bps: { label: "Treasury Ratio",    min: 1000, max: 9000, unit: "bps",     desc: "% of treasury ETH held as stable reserve." },
};

const DEFAULT_PARAMS: Params = {
  mint_factor: 100, burn_rate_bps: 2, reward_alloc_bps: 3000,
  cashback_base_bps: 50, merchant_alloc_bps: 1000, treasury_ratio_bps: 6000,
};

export default function AgentPage() {
  const [obs, setObs]               = useState<any>(null);
  const [simObs, setSimObs]         = useState<any>(null);
  const [params, setParams]         = useState<Params>(DEFAULT_PARAMS);
  const [draft, setDraft]           = useState<Params>(DEFAULT_PARAMS);
  const [modelStatus, setModelStatus] = useState<any>(null);
  const [loading, setLoading]       = useState(true);
  const [saving, setSaving]         = useState(false);
  const [burnLoading, setBurnLoading] = useState(false);
  const [mintLoading, setMintLoading] = useState(false);
  const [mintAmount, setMintAmount] = useState("10000");
  const [feedback, setFeedback]     = useState<{ msg: string; ok: boolean } | null>(null);
  const [loopRunning, setLoopRunning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Load chain state + model status + simulation state in parallel
      const [protState, mStatus, simState] = await Promise.allSettled([
        api.protocolState(),
        modelApi.status(),
        api.simState(),
      ]);

      if (protState.status === "fulfilled") {
        setObs(protState.value);
        const p: Params = protState.value.rl_parameters ?? DEFAULT_PARAMS;
        setParams(p);
        setDraft(p);
      }

      // Use simulation state for live economy metrics (chain data is often 0 on testnet)
      if (simState.status === "fulfilled") {
        setSimObs(simState.value);
      }

      if (mStatus.status === "fulfilled") {
        setModelStatus(mStatus.value);
        setLoopRunning(mStatus.value.loop_running ?? false);
        // If model has a last_action, use it as the live params
        if (mStatus.value.last_action) {
          setParams(mStatus.value.last_action);
          setDraft(mStatus.value.last_action);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    // Poll model status + simulation every 10s
    const t = setInterval(() => {
      modelApi.status().then(s => {
        setModelStatus(s);
        setLoopRunning(s.loop_running ?? false);
        if (s.last_action) setParams(s.last_action);
      }).catch(() => {});
      api.simState().then(s => setSimObs(s)).catch(() => {});
    }, 10000);
    return () => clearInterval(t);
  }, [load]);

  function flash(msg: string, ok: boolean) {
    setFeedback({ msg, ok });
    setTimeout(() => setFeedback(null), 4000);
  }

  async function saveParams() {
    setSaving(true);
    try {
      const r = await api.updateParams(draft);
      setParams(draft);
      flash(`Parameters updated${r.status === "on_chain" ? " on-chain" : " (simulated)"} ✓`, true);
    } catch (e: any) {
      flash(e.message ?? "Update failed", false);
    } finally {
      setSaving(false);
    }
  }

  async function runStep() {
    setSaving(true);
    try {
      const r = await modelApi.step();
      setParams(r.params);
      setDraft(r.params);
      setModelStatus((p: any) => ({ ...p, step_count: r.step, last_action: r.params }));
      flash(`RL step ${r.step} ✓ — policy: ${r.source} — pushed to chain`, true);
    } catch (e: any) {
      flash("Model server not reachable: " + (e.message ?? ""), false);
    } finally {
      setSaving(false);
    }
  }

  async function toggleLoop() {
    try {
      if (loopRunning) {
        await modelApi.stopLoop();
        setLoopRunning(false);
        flash("RL loop stopped", true);
      } else {
        await modelApi.startLoop();
        setLoopRunning(true);
        flash("RL loop started — running every 30s", true);
      }
    } catch (e: any) {
      flash("Model server not reachable", false);
    }
  }

  async function triggerBurn() {
    setBurnLoading(true);
    try {
      const r = await api.triggerBurn();
      flash(`Burn executed — ${r.paytkn_burned ?? "?"} PAYTKN burned ${r.status === "simulated" ? "(simulated)" : "on-chain"} ✓`, true);
    } catch (e: any) {
      flash(e.message ?? "Burn failed", false);
    } finally {
      setBurnLoading(false);
    }
  }

  async function triggerMint() {
    setMintLoading(true);
    try {
      const r = await api.triggerMint(parseInt(mintAmount));
      flash(`Mint executed — ${r.paytkn_minted ?? mintAmount} PAYTKN ${r.status === "simulated" ? "(simulated)" : "on-chain"} ✓`, true);
    } catch (e: any) {
      flash(e.message ?? "Mint failed", false);
    } finally {
      setMintLoading(false);
    }
  }

  if (loading) return (
    <div className="flex justify-center h-64 items-center">
      <div className="animate-spin h-10 w-10 rounded-full border-b-2 border-indigo-500" />
    </div>
  );

  const radarData = (Object.keys(PARAM_META) as Array<keyof Params>).map(key => ({
    param: PARAM_META[key].label.split(" ")[0],
    value: ((draft[key] - PARAM_META[key].min) / (PARAM_META[key].max - PARAM_META[key].min)) * 100,
  }));

  const modelConnected = !!modelStatus?.model_loaded;
  const policy = modelStatus?.policy ?? "unknown";

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold">RL Agent Control Panel</h1>
          <p className="text-gray-400 mt-1">PPO model controlling protocol economics live on Base Sepolia</p>
        </div>
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-2 px-4 py-2 rounded-full border text-sm font-medium ${
            modelConnected ? "bg-green-500/10 border-green-500/30 text-green-400" : "bg-red-500/10 border-red-500/30 text-red-400"}`}>
            <span className={`w-2 h-2 rounded-full ${modelConnected ? "bg-green-400 animate-pulse" : "bg-red-400"}`} />
            {modelConnected ? `PPO Model Connected` : "Model Offline"}
          </div>
          <button onClick={load} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors">
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Feedback */}
      {feedback && (
        <div className={`rounded-xl px-5 py-3 text-sm font-medium ${feedback.ok
          ? "bg-green-500/15 border border-green-500/30 text-green-400"
          : "bg-red-500/15 border border-red-500/30 text-red-400"}`}>
          {feedback.msg}
        </div>
      )}

      {/* Model status bar */}
      {modelStatus && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-4 flex-wrap">
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">Policy</div>
                <div className="font-bold text-white capitalize">{policy === "ppo" ? "PPO Neural Network" : "Rule-Based Heuristic"}</div>
              </div>
              {modelStatus.model_path && (
                <div>
                  <div className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">Model File</div>
                  <div className="text-sm text-indigo-400 font-mono">{modelStatus.model_path.split(/[\\/]/).slice(-2).join("/")}</div>
                </div>
              )}
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">Steps Run</div>
                <div className="font-bold text-white">{modelStatus.step_count ?? 0}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">Loop</div>
                <div className={`font-bold ${loopRunning ? "text-green-400" : "text-gray-400"}`}>
                  {loopRunning ? "Running (30s)" : "Stopped"}
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={runStep} disabled={saving}
                className="px-4 py-2 bg-indigo-700 hover:bg-indigo-600 disabled:bg-gray-700 text-white text-sm font-semibold rounded-lg transition-colors">
                {saving ? "Running…" : "▶ Run Step"}
              </button>
              <button onClick={toggleLoop}
                className={`px-4 py-2 text-white text-sm font-semibold rounded-lg transition-colors ${
                  loopRunning ? "bg-red-700 hover:bg-red-600" : "bg-green-700 hover:bg-green-600"}`}>
                {loopRunning ? "⏹ Stop Loop" : "⟳ Start Loop"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Observation stats — prefer simulation state, fall back to on-chain */}
      {(obs || simObs) && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Token Price"
            value={`$${Number(simObs?.token_price_usd ?? obs?.token?.price_usd ?? 1).toFixed(4)}`}
            color="indigo"
            sub={simObs ? "sim economy" : "on-chain"}
          />
          <StatCard
            label="Total Staked"
            value={Number(simObs?.staking_pool ?? obs?.staking?.total_staked ?? 0).toLocaleString()}
            color="blue"
            sub="PAYTKN"
          />
          <StatCard
            label="Treasury ETH"
            value={`${Number(simObs?.treasury_eth ?? obs?.treasury?.stable_reserve_eth ?? 0).toFixed(4)}`}
            color="green"
            sub="ETH reserve"
          />
          <StatCard
            label="Current APY"
            value={`${Number(simObs?.current_apy_pct ?? obs?.staking?.current_apy_pct ?? 0).toFixed(1)}%`}
            color="yellow"
          />
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* Parameter sliders */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-1">
            Live Parameters
            <span className="ml-2 text-xs text-yellow-400 font-normal">⚠ Override RL agent</span>
          </h2>
          <p className="text-xs text-gray-500 mb-5">Normally set by PPO agent. Manual override pushes directly on-chain with simulation fallback.</p>

          <div className="space-y-5">
            {(Object.keys(PARAM_META) as Array<keyof Params>).map(key => {
              const meta = PARAM_META[key];
              const val  = draft[key];
              const pct  = ((val - meta.min) / (meta.max - meta.min)) * 100;
              const agentVal = params[key];
              const isDiff = val !== agentVal;
              return (
                <div key={key}>
                  <div className="flex justify-between items-start mb-1">
                    <div>
                      <div className="text-sm text-gray-300 font-medium">{meta.label}</div>
                      <div className="text-xs text-gray-500">{meta.desc}</div>
                    </div>
                    <div className="text-right ml-4 shrink-0">
                      <span className={`font-mono text-sm ${isDiff ? "text-yellow-400" : "text-indigo-300"}`}>
                        {val} {meta.unit}
                      </span>
                      {isDiff && (
                        <div className="text-xs text-gray-600">RL: {agentVal}</div>
                      )}
                    </div>
                  </div>
                  <input type="range" min={meta.min} max={meta.max} value={val}
                    onChange={e => setDraft(d => ({ ...d, [key]: parseInt(e.target.value) }))}
                    className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-indigo-500"
                    style={{ background: `linear-gradient(to right, ${isDiff ? "#eab308" : "#6366f1"} ${pct}%, #374151 ${pct}%)` }}
                  />
                  <div className="flex justify-between text-xs text-gray-700 mt-0.5">
                    <span>{meta.min}</span><span>{meta.max}</span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex gap-3 mt-6">
            <button onClick={() => setDraft(params)} className="flex-1 border border-gray-700 hover:bg-gray-800 text-gray-300 py-2.5 rounded-lg text-sm transition-colors">
              Reset to RL Values
            </button>
            <button onClick={saveParams} disabled={saving}
              className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2">
              {saving ? <><div className="animate-spin h-3.5 w-3.5 rounded-full border-b-2 border-white"/>Saving…</> : "Apply On-Chain"}
            </button>
          </div>
        </div>

        {/* Radar chart */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4">Parameter Radar</h2>
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="#374151" />
              <PolarAngleAxis dataKey="param" tick={{ fill: "#9ca3af", fontSize: 12 }} />
              <Radar name="Current" dataKey="value" stroke="#6366f1" fill="#6366f1" fillOpacity={0.25} />
              <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151" }}
                formatter={(v: any) => [`${Number(v).toFixed(1)}%`, "Intensity"]} />
            </RadarChart>
          </ResponsiveContainer>
          <p className="text-xs text-gray-500 text-center mt-2">Values normalised 0–100% within valid bounds</p>

          {/* Last action from model */}
          {modelStatus?.last_action && (
            <div className="mt-4 bg-indigo-500/5 border border-indigo-500/20 rounded-xl p-3">
              <div className="text-xs text-indigo-400 font-semibold mb-2">🤖 Last RL Action (Step {modelStatus.step_count})</div>
              <div className="grid grid-cols-2 gap-1.5">
                {Object.entries(modelStatus.last_action).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-xs">
                    <span className="text-gray-500">{PARAM_META[k as keyof Params]?.label.split(" ")[0]}</span>
                    <span className="text-indigo-300 font-mono">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Manual actions */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Manual Agent Actions</h2>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-gray-800 rounded-xl p-5">
            <div className="text-2xl mb-2">🔥</div>
            <h3 className="font-semibold text-white">Execute Daily Burn</h3>
            <p className="text-sm text-gray-400 mt-1 mb-4">
              Burn <span className="text-red-400 font-mono">{draft.burn_rate_bps} bps</span> of supply. Normally triggered daily by the RL agent.
            </p>
            <button onClick={triggerBurn} disabled={burnLoading}
              className="w-full bg-red-700 hover:bg-red-600 disabled:bg-gray-700 text-white font-semibold py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2">
              {burnLoading ? <><div className="animate-spin h-4 w-4 rounded-full border-b-2 border-white"/>Burning…</> : "Trigger Burn"}
            </button>
          </div>
          <div className="bg-gray-800 rounded-xl p-5">
            <div className="text-2xl mb-2">⛏️</div>
            <h3 className="font-semibold text-white">Execute Mint</h3>
            <p className="text-sm text-gray-400 mt-1 mb-3">Agent mints when demand signals exceed supply pressure.</p>
            <div className="flex gap-2">
              <input value={mintAmount} onChange={e => setMintAmount(e.target.value)}
                className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
                placeholder="PAYTKN amount" type="number" />
              <button onClick={triggerMint} disabled={mintLoading}
                className="bg-green-700 hover:bg-green-600 disabled:bg-gray-700 text-white font-semibold px-4 py-2 rounded-lg text-sm transition-colors flex items-center gap-2">
                {mintLoading ? <div className="animate-spin h-3.5 w-3.5 rounded-full border-b-2 border-white"/> : "Mint"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* PPO explanation */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-3">About the PPO Agent</h2>
        <div className="grid md:grid-cols-3 gap-4 text-sm text-gray-400">
          <div>
            <span className="text-indigo-400 font-semibold">Observation Space (10D)</span><br />
            Token price, treasury ETH/PAYTKN, staking ratio, reward pool, APY, total supply, payment count, payment volume, current burn rate, reward allocation — normalised continuous values.
          </div>
          <div>
            <span className="text-indigo-400 font-semibold">Action Space (6D continuous)</span><br />
            One action per parameter, mapped from [-1,1] to valid bounds. PPO clips updates with ε=0.2. Network: [256, 256, 128] hidden layers. Trained 5M steps with curriculum.
          </div>
          <div>
            <span className="text-indigo-400 font-semibold">Reward Function</span><br />
            Price stability (+), staking growth (+), treasury health (+), excessive inflation (−), low liquidity (−). 45% bear-weighted curriculum for robustness across all market conditions.
          </div>
        </div>
      </div>
    </div>
  );
}
