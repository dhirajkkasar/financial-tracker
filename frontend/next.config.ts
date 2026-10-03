import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  output: 'export',
  // Pin Turbopack's root to this directory: a stray package-lock.json in a
  // parent dir (e.g. $HOME) otherwise makes Next infer the wrong workspace
  // root and CSS @import "tailwindcss" fails to resolve.
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
