"use client";
import { Suspense, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAccount, useWriteContract, useWaitForTransactionReceipt, useReadContract } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { parseEther, formatEther } from "viem";
import { GATEWAY_ADDRESS, GATEWAY_ABI, GATEWAY_RATE, CONTRACT_ADDRESSES, ERC20_ABI } from "@/lib/web3";

// ─────────────────────────────────────────────────────────────────────────────
// Types & constants
// ─────────────────────────────────────────────────────────────────────────────
type Step = "connect" | "select" | "review" | "signing" | "confirming" | "done" | "error";

// Testnet demo ETH prices — small amounts users can actually afford on Base Sepolia
const DEMO_ETH_PRICES: Record<string, number> = {
  "default":                    0.001,
  "MacBook Pro 14\"":           0.005,
  'MacBook Pro 14"':            0.005,
  "iPhone 15 Pro":              0.003,
  "Sony WH-1000XM5":           0.001,
  'iPad Pro 12.9"':             0.004,
  'iPad Pro 12.9\"':            0.004,
  "Samsung 4K Monitor 27\"":    0.002,
  "Mechanical Keyboard":        0.001,
  "Logitech MX Master 3S":      0.001,
  "AirPods Pro 2nd Gen":        0.001,
  "TechMart Pro":               0.001,
  "TechMart Business":          0.002,
  "TechMart Annual":            0.005,
};

function getDemoEth(productName: string): number {
  return DEMO_ETH_PRICES[productName] ?? DEMO_ETH_PRICES["default"];
}

// ─────────────────────────────────────────────────────────────────────────────
// Inner component
// ─────────────────────────────────────────────────────────────────────────────
function CheckoutInner() {
  const params   = useSearchParams();
  const { address, isConnected } = useAccount();

  const productName    = params.get("product")       ?? "PAYTKN Payment";
  const priceUSD       = parseFloat(params.get("price") ?? "0");
  const merchantAddr   = params.get("merchant")      ?? "0x0000000000000000000000000000000000000000";
  const merchantName   = params.get("merchant_name") ?? "Merchant";
  const description    = params.get("description")   ?? "";
  const emoji          = params.get("emoji")         ?? "🛒";
  const payType        = params.get("type")          ?? "one-time";
  const period         = params.get("period")        ?? "monthly";
  const isSubscription = payType === "subscription";

  // eth_amount from URL (set by store) takes priority over product-name lookup
  const ethAmountParam = params.get("eth_amount");
  const ethAmount = ethAmountParam
    ? parseFloat(ethAmountParam)
    : getDemoEth(productName);
  const paytknToMerchant = ethAmount * 0.995 * GATEWAY_RATE; // after 0.5% fee

  const [step, setStep] = useState<Step>("connect");
  const [errorMsg, setErrorMsg] = useState("");

  // ── Wallet connect step ──────────────────────────────────────────────────
  useEffect(() => {
    if (isConnected && step === "connect") setStep("select");
  }, [isConnected, step]);

  // ── wagmi: write contract ────────────────────────────────────────────────
  const {
    writeContract,
    data: txHash,
    isPending: isWritePending,
    error: writeError,
    reset: resetWrite,
  } = useWriteContract();

  // ── wagmi: wait for confirmation ──────────────────────────────────────────
  const {
    isLoading: isConfirming,
    isSuccess: isConfirmed,
    data: receipt,
  } = useWaitForTransactionReceipt({ hash: txHash });

  // ── PAYTKN balance of merchant ────────────────────────────────────────────
  const { data: merchantPAYTKN } = useReadContract({
    address: CONTRACT_ADDRESSES.token as `0x${string}`,
    abi: ERC20_ABI,
    functionName: "balanceOf",
    args: [merchantAddr as `0x${string}`],
    query: { enabled: !!merchantAddr && merchantAddr.startsWith("0x") && merchantAddr.length === 42 },
  });

  // Advance step when MetaMask is awaiting signature
  useEffect(() => {
    if (isWritePending && step === "review") setStep("signing");
  }, [isWritePending, step]);

  // Advance to confirming once tx is broadcast
  useEffect(() => {
    if (txHash && step === "signing") setStep("confirming");
  }, [txHash, step]);

  // Done once mined
  useEffect(() => {
    if (isConfirmed && step === "confirming") setStep("done");
  }, [isConfirmed, step]);

  // Handle write errors
  useEffect(() => {
    if (writeError) {
      setErrorMsg(writeError.message.split("\n")[0]);
      setStep("error");
    }
  }, [writeError]);

  // ── Pay handler — triggers real MetaMask popup ───────────────────────────
  function handlePay() {
    if (!address) return;
    setStep("review"); // will advance to "signing" via useEffect when isPending
    writeContract({
      address: GATEWAY_ADDRESS,
      abi: GATEWAY_ABI,
      functionName: "pay",
      args: [merchantAddr as `0x${string}`],
      value: parseEther(ethAmount.toFixed(18).replace(/\.?0+$/, "")),
    });
  }

  function reset() {
    resetWrite();
    setStep("select");
    setErrorMsg("");
  }

  // ── Progress steps ────────────────────────────────────────────────────────
  const progressSteps: { key: Step; label: string }[] = [
    { key: "select",     label: "Review" },
    { key: "signing",    label: "Sign" },
    { key: "confirming", label: "Confirm" },
    { key: "done",       label: "Done" },
  ];
  const stepIdx = progressSteps.findIndex(s => s.key === step);

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-[85vh] flex items-start justify-center pt-8 px-4">
      <div className="w-full max-w-lg space-y-4">

        {/* Product card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">

          {/* Merchant header */}
          <div className="bg-gradient-to-r from-indigo-900/60 to-purple-900/40 px-6 py-5 border-b border-gray-800">
            <div className="flex items-center gap-4">
              <span className="text-5xl">{emoji}</span>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-gray-400">{merchantName}</div>
                <div className="font-bold text-white text-lg leading-tight">{productName}</div>
                <div className="text-gray-400 text-sm truncate">{description}</div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-2xl font-bold text-white">${priceUSD.toLocaleString()}</div>
                {isSubscription && <div className="text-xs text-indigo-400">/{period}</div>}
              </div>
            </div>
          </div>

          {/* Progress bar */}
          {step !== "connect" && step !== "done" && step !== "error" && (
            <div className="px-6 py-3 border-b border-gray-800">
              <div className="flex items-center justify-between">
                {progressSteps.map((s, i) => (
                  <div key={s.key} className="flex items-center">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                      i < stepIdx ? "bg-green-500 text-white" :
                      i === stepIdx ? "bg-indigo-600 text-white ring-2 ring-indigo-400/40" :
                      "bg-gray-800 text-gray-600"}`}>
                      {i < stepIdx ? "✓" : i + 1}
                    </div>
                    {i < progressSteps.length - 1 && (
                      <div className={`h-0.5 w-8 mx-1 transition-colors ${i < stepIdx ? "bg-green-500" : "bg-gray-800"}`} />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="p-6 space-y-5">

            {/* ── CONNECT ─────────────────────────────────────────────── */}
            {step === "connect" && (
              <div className="flex flex-col items-center gap-5 py-6">
                <div className="text-5xl">👛</div>
                <div className="text-center">
                  <p className="font-semibold text-white text-lg">Connect your wallet</p>
                  <p className="text-gray-400 text-sm mt-1">Required to pay with crypto on Base Sepolia</p>
                </div>
                <ConnectButton />
              </div>
            )}

            {/* ── SELECT / REVIEW ──────────────────────────────────────── */}
            {(step === "select" || step === "review") && (
              <>
                {/* On-chain badge */}
                <div className="flex items-center gap-2 bg-green-900/20 border border-green-700/30 rounded-xl px-4 py-2.5">
                  <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                  <span className="text-xs text-green-400 font-medium">Real on-chain payment — Base Sepolia</span>
                </div>

                {/* Payment breakdown */}
                <div className="bg-gray-800 rounded-xl p-4 space-y-3 text-sm">
                  <div className="flex justify-between items-baseline">
                    <span className="text-gray-400">You send (ETH)</span>
                    <span className="text-white font-bold text-xl">{ethAmount} ETH</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Protocol fee (0.5%)</span>
                    <span className="text-gray-400">−{(ethAmount * 0.005).toFixed(6)} ETH</span>
                  </div>
                  <div className="border-t border-gray-700 pt-2 flex justify-between items-center">
                    <span className="text-gray-400 font-medium">Merchant receives</span>
                    <span className="text-emerald-400 font-bold text-lg">{paytknToMerchant.toFixed(3)} PAYTKN</span>
                  </div>
                  <div className="border-t border-gray-700 pt-2 flex items-start gap-2 bg-indigo-500/5 rounded-lg p-2 -mx-1">
                    <span className="text-indigo-400 text-sm mt-0.5">🤖</span>
                    <div>
                      <div className="text-xs font-semibold text-indigo-400">PAYTKN Cashback</div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        RL agent calculates your cashback based on staking tier and <code className="text-indigo-300">cashback_base_bps</code>. Sent to your wallet.
                      </div>
                    </div>
                  </div>
                </div>

                {/* Info rows */}
                <div className="space-y-2 text-sm">
                  {([
                    ["From wallet",   address ? `${address.slice(0,8)}…${address.slice(-6)}` : "-"],
                    ["To merchant",   merchantAddr ? `${merchantAddr.slice(0,8)}…${merchantAddr.slice(-6)}` : "-"],
                    ["ETH → PAYTKN",  `via PaytknGateway @ ${GATEWAY_RATE} PAYTKN/ETH`],
                    ["Settlement",    "Base Sepolia (Chain 84532)"],
                    ["Contract",      `${GATEWAY_ADDRESS.slice(0,10)}… ↗`],
                  ] as [string,string][]).map(([k,v]) => (
                    <div key={k} className="flex justify-between bg-gray-800 rounded-lg px-4 py-2.5">
                      <span className="text-gray-400">{k}</span>
                      <span className="font-medium text-white text-right max-w-[55%] truncate">{v}</span>
                    </div>
                  ))}
                </div>

                {/* Merchant current PAYTKN balance */}
                {merchantPAYTKN !== undefined && (
                  <div className="flex justify-between bg-emerald-900/20 border border-emerald-700/30 rounded-xl px-4 py-2.5 text-sm">
                    <span className="text-gray-400">Merchant current PAYTKN</span>
                    <span className="text-emerald-400 font-mono">{(Number(merchantPAYTKN) / 1e18).toFixed(4)} PAYTKN</span>
                  </div>
                )}

                <div className="flex gap-3">
                  <ConnectButton accountStatus="address" chainStatus="icon" showBalance={false} />
                  <button
                    onClick={handlePay}
                    disabled={step === "review"}
                    className={`flex-1 font-bold py-3.5 rounded-xl transition-all text-sm ${
                      step === "review"
                        ? "bg-indigo-800/60 text-indigo-300 cursor-wait"
                        : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-900/40"
                    }`}
                  >
                    {step === "review"
                      ? <span className="flex items-center justify-center gap-2">
                          <span className="w-4 h-4 border-2 border-indigo-400/40 border-t-indigo-300 rounded-full animate-spin" />
                          Opening MetaMask…
                        </span>
                      : isSubscription
                        ? `⚡ Subscribe — ${ethAmount} ETH`
                        : `⚡ Pay ${ethAmount} ETH on-chain`
                    }
                  </button>
                </div>
              </>
            )}

            {/* ── SIGNING — waiting for MetaMask ───────────────────────── */}
            {step === "signing" && (
              <div className="flex flex-col items-center gap-5 py-10">
                <div className="w-20 h-20 rounded-2xl bg-amber-600/20 border border-amber-500/40 flex items-center justify-center text-4xl animate-pulse">
                  🦊
                </div>
                <div className="text-center">
                  <p className="font-semibold text-white text-lg">Approve in MetaMask</p>
                  <p className="text-sm text-gray-400 mt-1">Review the transaction details and confirm</p>
                </div>
                <div className="bg-gray-800 rounded-xl p-4 w-full space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Sending</span>
                    <span className="text-white font-mono">{ethAmount} ETH</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">To contract</span>
                    <span className="text-indigo-400 font-mono">{GATEWAY_ADDRESS.slice(0,14)}…</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Merchant gets</span>
                    <span className="text-emerald-400 font-mono">{paytknToMerchant.toFixed(3)} PAYTKN</span>
                  </div>
                </div>
                <p className="text-xs text-gray-500">Check MetaMask window / extension popup</p>
              </div>
            )}

            {/* ── CONFIRMING — waiting for block ───────────────────────── */}
            {step === "confirming" && (
              <div className="flex flex-col items-center gap-6 py-8">
                <div className="relative w-20 h-20">
                  <div className="absolute inset-0 rounded-full border-4 border-gray-800" />
                  <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-indigo-500 animate-spin" />
                  <div className="w-20 h-20 flex items-center justify-center text-2xl">⛓️</div>
                </div>
                <div className="text-center">
                  <p className="font-semibold text-white text-lg">Broadcasting to Base Sepolia</p>
                  <p className="text-sm text-gray-400 mt-1">Waiting for block confirmation…</p>
                </div>
                {txHash && (
                  <a
                    href={`https://sepolia.basescan.org/tx/${txHash}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-400 hover:text-blue-300 font-mono underline"
                  >
                    {txHash.slice(0, 20)}… → View on Basescan ↗
                  </a>
                )}
                <div className="w-full bg-gray-800 rounded-xl p-3 space-y-1.5 text-xs text-gray-500">
                  <div className="flex items-center gap-2"><span className="text-green-400">✓</span> MetaMask signed</div>
                  <div className="flex items-center gap-2"><span className="text-green-400">✓</span> Transaction broadcast</div>
                  <div className="flex items-center gap-2"><span className="animate-spin inline-block">⏳</span> Waiting for block inclusion…</div>
                  <div className="flex items-center gap-2"><span className="text-indigo-400">🤖</span> RL agent calculating cashback…</div>
                </div>
              </div>
            )}

            {/* ── DONE ─────────────────────────────────────────────────── */}
            {step === "done" && (
              <div className="space-y-5">
                <div className="flex flex-col items-center gap-3 py-4">
                  <div className="w-20 h-20 rounded-full bg-green-500/20 border-2 border-green-500 flex items-center justify-center text-4xl">✓</div>
                  <p className="text-2xl font-bold text-white">
                    {isSubscription ? "Subscribed!" : "Payment Complete!"}
                  </p>
                  <p className="text-sm text-gray-400 text-center">
                    Transaction confirmed on Base Sepolia.
                  </p>
                </div>

                <div className="bg-gray-800 rounded-xl p-4 space-y-3 text-sm">
                  {/* Merchant PAYTKN */}
                  <div className="flex justify-between items-center bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3">
                    <div>
                      <div className="text-emerald-400 font-semibold text-xs uppercase tracking-wider">🏪 Merchant received</div>
                      <div className="text-xs text-gray-400 mt-0.5">PAYTKN sent to merchant wallet</div>
                    </div>
                    <span className="text-emerald-400 font-bold text-lg ml-4">
                      +{paytknToMerchant.toFixed(3)} PAYTKN
                    </span>
                  </div>

                  {/* RL Cashback */}
                  <div className="flex justify-between items-center bg-indigo-500/10 border border-indigo-500/20 rounded-lg p-3">
                    <div>
                      <div className="text-indigo-400 font-semibold text-xs uppercase tracking-wider">🤖 Your cashback</div>
                      <div className="text-xs text-gray-400 mt-0.5">RL agent mints to your wallet</div>
                    </div>
                    <span className="text-indigo-400 font-bold text-lg ml-4">Check wallet ✓</span>
                  </div>

                  {/* Tx hash */}
                  {txHash && (
                    <a
                      href={`https://sepolia.basescan.org/tx/${txHash}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-between bg-gray-700 rounded-lg px-4 py-2.5 hover:bg-gray-600 transition-colors group"
                    >
                      <span className="text-gray-400 text-xs">Transaction</span>
                      <span className="text-blue-400 font-mono text-xs group-hover:text-blue-300">
                        {txHash.slice(0, 18)}… ↗
                      </span>
                    </a>
                  )}

                  {/* Current merchant balance */}
                  {merchantPAYTKN !== undefined && (
                    <div className="flex justify-between bg-gray-700 rounded-lg px-4 py-2.5">
                      <span className="text-gray-400 text-xs">Merchant balance now</span>
                      <span className="text-emerald-400 font-mono text-xs">{(Number(merchantPAYTKN) / 1e18).toFixed(4)} PAYTKN</span>
                    </div>
                  )}

                  <div className="flex justify-between bg-gray-700 rounded-lg px-4 py-2.5">
                    <span className="text-gray-400 text-xs">Block</span>
                    <span className="text-white font-mono text-xs">#{receipt?.blockNumber?.toString()}</span>
                  </div>
                </div>

                <div className="flex gap-3">
                  <a href="/dashboard"
                    className="flex-1 text-center border border-gray-700 text-gray-400 hover:text-white hover:border-gray-600 py-3 rounded-xl text-sm transition-colors">
                    My Dashboard
                  </a>
                  <button onClick={reset}
                    className="flex-1 bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl text-sm">
                    Pay Again
                  </button>
                </div>
              </div>
            )}

            {/* ── ERROR ────────────────────────────────────────────────── */}
            {step === "error" && (
              <div className="space-y-4 py-4">
                <div className="flex flex-col items-center gap-3">
                  <div className="w-16 h-16 rounded-full bg-red-500/20 border-2 border-red-500/50 flex items-center justify-center text-3xl">✗</div>
                  <p className="font-bold text-white text-lg">Transaction Failed</p>
                </div>
                <div className="bg-red-900/20 border border-red-700/40 rounded-xl px-4 py-3">
                  <p className="text-red-300 text-sm break-words">{errorMsg || "User rejected or insufficient ETH balance."}</p>
                </div>
                <div className="bg-gray-800 rounded-xl px-4 py-3 text-xs space-y-1.5 text-gray-400">
                  <p className="font-semibold text-gray-300">Common fixes:</p>
                  <p>• Make sure you're on <strong>Base Sepolia</strong> (Chain 84532) in MetaMask</p>
                  <p>• You need at least <strong>{(ethAmount + 0.001).toFixed(4)} ETH</strong> (payment + gas)</p>
                  <p>• Get test ETH from: <a href="https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet" className="text-blue-400 underline" target="_blank">Coinbase Faucet</a></p>
                </div>
                <button onClick={reset}
                  className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl">
                  Try Again
                </button>
              </div>
            )}

          </div>
        </div>

        {/* Network footer */}
        <div className="flex items-center justify-center gap-2 text-xs text-gray-600">
          <span className="w-2 h-2 rounded-full bg-green-500/60" />
          <span>Base Sepolia · Chain 84532</span>
          <span>·</span>
          <a href={`https://sepolia.basescan.org/address/${GATEWAY_ADDRESS}`}
            target="_blank" rel="noopener noreferrer"
            className="text-gray-500 hover:text-gray-400">
            PaytknGateway ↗
          </a>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
export default function CheckoutPage() {
  return (
    <Suspense fallback={
      <div className="min-h-[70vh] flex items-center justify-center">
        <div className="text-gray-500">Loading checkout…</div>
      </div>
    }>
      <CheckoutInner />
    </Suspense>
  );
}
