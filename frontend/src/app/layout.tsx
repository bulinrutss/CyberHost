import { publicAsset } from "@/lib/publicAsset";
import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AnalyticsTracker } from "@/components/AnalyticsTracker";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CyberHost — Hospedagem VPS Premium no Brasil",
  description:
    "A melhor hospedagem VPS do Brasil com NVMe, uptime garantido e suporte 24h. Painel de gerenciamento com provisionamento automático.",
  applicationName: "CyberHost",
  manifest: publicAsset("/manifest.webmanifest"),
  appleWebApp: {
    capable: true,
    title: "CyberHost",
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
    icon: publicAsset("/favicon.ico"),
    apple: publicAsset("/apple-touch-icon.png"),
  },
};

export const viewport: Viewport = {
  themeColor: "#06c96c",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

const themeScript = `(function(){try{var t=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',t)}catch(e){document.documentElement.setAttribute('data-theme','light')}})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={inter.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="font-sans">
        <ThemeProvider>
          <AnalyticsTracker />
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
