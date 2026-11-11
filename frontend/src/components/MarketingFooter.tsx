"use client";

import { useState } from "react";
import Link from "next/link";
import { CyberHostLogo } from "@/components/CyberHostLogo";
import { LegalModal } from "@/components/LegalModal";
import {
  LEGAL_CNPJ,
  LEGAL_CONTACT_EMAIL,
  LEGAL_UPDATED_AT,
  PRIVACY_POLICY,
  TERMS_OF_USE,
} from "@/lib/legal";

type LegalDoc = "terms" | "privacy" | null;

export function MarketingFooter() {
  const [doc, setDoc] = useState<LegalDoc>(null);

  return (
    <>
      <footer className="marketing-footer border-t border-[var(--glass-border)] mt-20">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-12">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-10 mb-10">
            <div>
              <CyberHostLogo href="/" height={52} />
              <p className="text-sm text-[var(--text-muted)] mt-4 leading-relaxed">
                A melhor infraestrutura de hospedagem do Brasil
              </p>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Produtos</h4>
              <ul className="space-y-2 text-sm text-[var(--text-secondary)]">
                <li>
                  <a href="#recursos" className="hover:text-[var(--accent)]">
                    VPS Cloud
                  </a>
                </li>
                <li>
                  <a href="#planos" className="hover:text-[var(--accent)]">
                    Planos VPS
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Suporte</h4>
              <ul className="space-y-2 text-sm text-[var(--text-secondary)]">
                <li>
                  <a
                    href={`mailto:${LEGAL_CONTACT_EMAIL}`}
                    className="hover:text-[var(--accent)]"
                  >
                    {LEGAL_CONTACT_EMAIL}
                  </a>
                </li>
                <li>
                  <a
                    href="https://discord.gg/Zz4eJbTdsw"
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-[var(--accent)]"
                  >
                    Discord
                  </a>
                </li>
                <li>
                  <Link href="/login" className="hover:text-[var(--accent)]">
                    Área do cliente
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Empresa</h4>
              <ul className="space-y-2 text-sm text-[var(--text-secondary)]">
                <li>CyberHost — Hospedagem VPS Premium</li>
                <li>Servidores no Brasil</li>
                <li>
                  <button
                    type="button"
                    className="hover:text-[var(--accent)] text-left"
                    onClick={() => setDoc("terms")}
                  >
                    Termos de uso
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    className="hover:text-[var(--accent)] text-left"
                    onClick={() => setDoc("privacy")}
                  >
                    Política de privacidade
                  </button>
                </li>
              </ul>
            </div>
          </div>
          <div className="text-center text-xs text-[var(--text-muted)] pt-6 border-t border-[var(--glass-border)] space-y-1">
            <p>© {new Date().getFullYear()} CyberHost — Todos os direitos reservados</p>
            <p>CNPJ {LEGAL_CNPJ}</p>
          </div>
        </div>
      </footer>

      <LegalModal
        open={doc === "terms"}
        title="Termos de uso"
        updatedAt={LEGAL_UPDATED_AT}
        sections={TERMS_OF_USE}
        onClose={() => setDoc(null)}
      />
      <LegalModal
        open={doc === "privacy"}
        title="Política de privacidade"
        updatedAt={LEGAL_UPDATED_AT}
        sections={PRIVACY_POLICY}
        onClose={() => setDoc(null)}
      />
    </>
  );
}
