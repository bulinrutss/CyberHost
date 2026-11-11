"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  SvgChat,
  SvgChevronDown,
  SvgCloud,
  SvgCog,
  SvgGlobe,
  SvgPlus,
  SvgServer,
  SvgUser,
} from "@/components/ui/svgs";
import { api, clearToken, getToken, type User } from "@/lib/api";
import { WEB_HOSTING_ENABLED } from "@/lib/features";
import { formatPhoneDisplay } from "@/lib/phone";
import { HostPushToggle } from "@/components/HostPushToggle";

type MenuItem = {
  href: string;
  label: string;
  svg: React.ReactNode;
  adminOnly?: boolean;
  clientOnly?: boolean;
  isActive?: (pathname: string) => boolean;
};

const menuItems: MenuItem[] = [
  {
    href: "/account",
    label: "Perfil",
    svg: <SvgUser className="w-5 h-5" />,
  },
  {
    href: "/dashboard",
    label: "Meus servidores",
    clientOnly: true,
    svg: <SvgServer className="w-5 h-5" />,
    isActive: (pathname) => pathname === "/dashboard" || pathname.startsWith("/dashboard/vps/"),
  },
  ...(WEB_HOSTING_ENABLED
    ? [
        {
          href: "/dashboard/sites",
          label: "Sites",
          clientOnly: true,
          svg: <SvgGlobe className="w-5 h-5" />,
          isActive: (pathname) => pathname.startsWith("/dashboard/sites"),
        } satisfies MenuItem,
      ]
    : []),
  {
    href: "/dashboard/files",
    label: "CyberCloud (20 GB+)",
    clientOnly: true,
    svg: <SvgCloud className="w-5 h-5" />,
    isActive: (pathname) => pathname.startsWith("/dashboard/files"),
  },
  {
    href: "/order",
    label: "Nova VPS",
    clientOnly: true,
    svg: <SvgPlus className="w-5 h-5" />,
  },
  {
    href: "/dashboard/support",
    label: "Suporte",
    clientOnly: true,
    svg: <SvgChat className="w-5 h-5" />,
  },
  {
    href: "/admin?tab=support",
    label: "Suporte",
    adminOnly: true,
    svg: <SvgChat className="w-5 h-5" />,
  },
  {
    href: "/admin",
    label: "Painel admin",
    adminOnly: true,
    svg: <SvgCog className="w-5 h-5" />,
  },
];

function displayName(user: User) {
  const first = user.name.trim().split(/\s+/)[0];
  return first || formatPhoneDisplay(user.phone);
}

function initials(user: User) {
  const parts = user.name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return user.phone.slice(-2);
}

export function UserAccountMenu() {
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    api.me()
      .then(setUser)
      .catch(() => setUser(null));
  }, [pathname]);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const logout = () => {
    void api.logout().catch(() => undefined);
    clearToken();
    setUser(null);
    setOpen(false);
    router.push("/");
  };

  if (!user) return null;

  const name = displayName(user);
  const items = menuItems.filter((item) => {
    if (item.adminOnly) return user.is_admin;
    if (item.clientOnly) return !user.is_admin;
    return true;
  });

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2.5 pl-2 pr-3 py-1.5 rounded-lg hover:bg-[var(--glass-bg)] transition-colors text-left"
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span className="w-9 h-9 rounded-full bg-[var(--bg-elevated)] border border-[var(--glass-border)] flex items-center justify-center text-[var(--text-muted)]">
          <SvgUser className="w-5 h-5" />
        </span>
        <span className="hidden sm:block leading-tight">
          <span className="block text-sm font-semibold text-[var(--text-primary)]">
            Olá, {name}
          </span>
          <span className="block text-xs text-[var(--text-muted)]">Minha conta</span>
        </span>
        <SvgChevronDown
          className={`w-4 h-4 text-[var(--text-muted)] transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="account-menu absolute right-0 top-full mt-2 w-[min(100vw-2rem,320px)] rounded-xl border border-[var(--glass-border)] bg-[var(--bg-base)] shadow-xl z-[100] overflow-hidden animate-in fade-in duration-150"
        >
          <div className="p-4 border-b border-[var(--glass-border)]">
            <div className="flex items-start gap-3">
              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-brand-500 to-brand-600 flex items-center justify-center text-white text-sm font-bold shrink-0">
                {initials(user)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-[var(--text-secondary)] leading-snug">
                  Bem-vindo novamente à CyberHost,{" "}
                  <span className="font-semibold text-[var(--text-primary)]">{name}</span>
                </p>
                <button
                  type="button"
                  onClick={logout}
                  className="text-sm font-medium text-[var(--accent)] hover:underline mt-1"
                >
                  Sair
                </button>
              </div>
            </div>
          </div>

          <ul className="py-2">
            {items.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  role="menuitem"
                  onClick={() => setOpen(false)}
                  className={`flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-[var(--bg-elevated)] transition-colors ${
                    (item.isActive ? item.isActive(pathname) : pathname === item.href)
                      ? "text-[var(--accent)]"
                      : "text-[var(--text-primary)]"
                  }`}
                >
                  <span className="text-[var(--text-muted)]">{item.svg}</span>
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
          <HostPushToggle />
        </div>
      )}
    </div>
  );
}
