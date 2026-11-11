"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { CyberHostLogo } from "@/components/CyberHostLogo";
import { DashboardTabs } from "@/components/DashboardTabs";
import { CyberHostPwa } from "@/components/CyberHostPwa";
import { ThemeToggle } from "@/components/ThemeToggle";
import { UserAccountMenu } from "@/components/UserAccountMenu";
import { api, getToken } from "@/lib/api";

type Props = {
  admin?: boolean;
};

export function Navbar({ admin }: Props) {
  const pathname = usePathname();
  const [logged, setLogged] = useState(false);
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    const token = !!getToken();
    setLogged(token);
    if (!token || admin) {
      setIsClient(false);
      return;
    }
    api
      .me()
      .then((user) => setIsClient(!user.is_admin))
      .catch(() => setIsClient(false));
  }, [pathname, admin]);

  return (
    <header className="glass-nav">
      <div className="max-w-cyber mx-auto px-4 sm:px-6 h-[72px] flex items-center gap-4">
        <CyberHostLogo href={logged ? (admin ? "/admin" : "/dashboard") : "/"} height={34} />

        {isClient && <DashboardTabs />}

        <nav className="flex items-center gap-2 sm:gap-3 ml-auto shrink-0">
          <CyberHostPwa />
          <ThemeToggle />
          {logged ? (
            <UserAccountMenu />
          ) : (
            <>
              <Link
                href="/login"
                className="px-3.5 py-2 rounded-lg text-sm font-medium text-secondary hover:text-[var(--accent)] transition-colors"
              >
                Entrar
              </Link>
              <Link href="/register" className="btn-primary !py-2 !px-4 text-sm hidden sm:inline-flex">
                Criar conta
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
