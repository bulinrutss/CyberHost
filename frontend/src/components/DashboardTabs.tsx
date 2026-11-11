"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SvgChat, SvgCloud, SvgDocument, SvgGame, SvgGlobe, SvgServer } from "@/components/ui/svgs";
import { GAME_HOSTING_ENABLED, WEB_HOSTING_ENABLED } from "@/lib/features";

type Tab = {
  href: string;
  label: string;
  shortLabel?: string;
  icon: typeof SvgServer;
  isActive: (pathname: string) => boolean;
};

const tabs: Tab[] = [
  {
    href: "/dashboard",
    label: "Meus servidores",
    shortLabel: "Servidores",
    icon: SvgServer,
    isActive: (pathname) =>
      pathname === "/dashboard" || pathname.startsWith("/dashboard/vps/"),
  },
  ...(GAME_HOSTING_ENABLED
    ? [
        {
          href: "/dashboard/games",
          label: "Servidores de jogo",
          shortLabel: "Jogos",
          icon: SvgGame,
          isActive: (pathname: string) => pathname.startsWith("/dashboard/games"),
        } satisfies Tab,
      ]
    : []),
  ...(WEB_HOSTING_ENABLED
    ? [
        {
          href: "/dashboard/sites",
          label: "Sites",
          shortLabel: "Sites",
          icon: SvgGlobe,
          isActive: (pathname: string) => pathname.startsWith("/dashboard/sites"),
        } satisfies Tab,
      ]
    : []),
  {
    href: "/dashboard/files",
    label: "CyberCloud",
    icon: SvgCloud,
    isActive: (pathname) => pathname.startsWith("/dashboard/files"),
  },
  {
    href: "/dashboard/orders",
    label: "Pedidos",
    icon: SvgDocument,
    isActive: (pathname) => pathname.startsWith("/dashboard/orders"),
  },
  {
    href: "/dashboard/support",
    label: "Suporte",
    icon: SvgChat,
    isActive: (pathname) => pathname.startsWith("/dashboard/support"),
  },
];

export function DashboardTabs() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-0.5 sm:gap-1 min-w-0 flex-1 overflow-x-auto" aria-label="Área do cliente">
      {tabs.map((tab) => {
        const active = tab.isActive(pathname);
        const Icon = tab.icon;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-2 rounded-lg text-sm font-medium transition-colors shrink-0 ${
              active
                ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                : "text-[var(--text-secondary)] hover:text-[var(--accent)] hover:bg-[var(--glass-bg)]"
            }`}
          >
            <Icon className="w-4 h-4" />
            <span className="hidden sm:inline">{tab.shortLabel ?? tab.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
