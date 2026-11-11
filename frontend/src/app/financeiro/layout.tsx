import { publicAsset } from "@/lib/publicAsset";
import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "Financeiro — ruts.dev",
  description: "Controle de gastos, entradas e agenda pessoal. Use no navegador ou instale como aplicativo.",
  applicationName: "Financeiro",
  manifest: publicAsset("/financeiro/manifest.webmanifest"),
  appleWebApp: {
    capable: true,
    title: "Financeiro",
    statusBarStyle: "default",
  },
  formatDetection: {
    telephone: false,
  },
  other: {
    "mobile-web-app-capable": "yes",
    "apple-mobile-web-app-capable": "yes",
  },
  icons: {
    apple: publicAsset("/financeiro/apple-touch-icon.png"),
    icon: [
      { url: publicAsset("/financeiro/icon-192.png"), sizes: "192x192", type: "image/png" },
      { url: publicAsset("/financeiro/icon-512.png"), sizes: "512x512", type: "image/png" },
    ],
  },
};

export const viewport: Viewport = {
  themeColor: "#06c96c",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function FinanceiroLayout({ children }: { children: React.ReactNode }) {
  return children;
}
