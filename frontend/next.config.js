const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
// Manter alinhado a frontend/src/lib/features.ts (GAME_HOSTING_ENABLED).
const GAME_HOSTING_ENABLED = false;

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    // basePath quebra o otimizador /_next/image; servir arquivos de public/ direto
    unoptimized: true,
  },
  ...(basePath
    ? {
        basePath,
        assetPrefix: basePath,
      }
    : {}),
  async headers() {
    return [
      {
        source: "/financeiro/sw.js",
        headers: [{ key: "Cache-Control", value: "no-cache, no-store, must-revalidate" }],
      },
      {
        source: "/sw.js",
        headers: [{ key: "Cache-Control", value: "no-cache, no-store, must-revalidate" }],
      },
    ];
  },
  async redirects() {
    if (GAME_HOSTING_ENABLED) return [];
    return [
      { source: "/order/game", destination: "/order", permanent: false },
      { source: "/order/game/:path*", destination: "/order", permanent: false },
      { source: "/dashboard/games", destination: "/dashboard", permanent: false },
      { source: "/dashboard/games/:path*", destination: "/dashboard", permanent: false },
    ];
  },
};

module.exports = nextConfig;
