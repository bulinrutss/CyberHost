"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { CyberHostLogo } from "@/components/CyberHostLogo";
import { CyberHostPwa } from "@/components/CyberHostPwa";
import { ThemeToggle } from "@/components/ThemeToggle";
import { UserAccountMenu } from "@/components/UserAccountMenu";
import { getToken } from "@/lib/api";

export function MarketingNavbar() {
  const pathname = usePathname();
  const [logged, setLogged] = useState(false);

  useEffect(() => {
    setLogged(!!getToken());
  }, [pathname]);

  return (
    <header className="marketing-nav sticky top-0 z-50">
      <div className="max-w-cyber mx-auto px-4 sm:px-6 h-[72px] flex items-center justify-between">
        <CyberHostLogo href="/" height={48} />

        <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-[var(--text-secondary)]">
          <a href="#inicio" className="hover:text-[var(--accent)] transition-colors">Início</a>
          <a href="#recursos" className="hover:text-[var(--accent)] transition-colors">Recursos</a>
          <a href="#tecnologias" className="hover:text-[var(--accent)] transition-colors">Tecnologias</a>
          <a href="https://discord.gg/Zz4eJbTdsw" target="_blank" rel="noreferrer" className="hover:text-[var(--accent)] transition-colors">
            Contato
          </a>
        </nav>

        <div className="flex items-center gap-3">
          <CyberHostPwa buttonClassName="btn-ghost-marketing text-sm !py-2" />
          <ThemeToggle variant="marketing" />
          {logged ? (
            <UserAccountMenu />
          ) : (
            <>
              <Link href="/login" className="btn-ghost-marketing text-sm">
                Entrar
              </Link>
              <Link href="/register" className="btn-primary !py-2 !px-5 text-sm hidden sm:inline-flex">
                Criar conta
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
