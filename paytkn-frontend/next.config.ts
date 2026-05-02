import type { NextConfig } from "next";

// Use a separate distDir per port so Next.js 16 allows two dev servers
// from the same codebase simultaneously (each gets its own lock file).
const port = process.env.PORT ?? "3000";
const distDir = port === "3001" ? ".next-merchant" : ".next";

const nextConfig: NextConfig = {
  distDir,
};

export default nextConfig;
