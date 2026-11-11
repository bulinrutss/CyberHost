"use client";

import { SupportInbox } from "@/components/SupportInbox";

export default function SupportPage() {
  return (
    <>
      <p className="text-sm font-medium text-[var(--accent)] mb-2 tracking-wide uppercase">
        Suporte
      </p>
      <h1 className="text-3xl font-bold tracking-tight mb-2">Tickets</h1>
      <p className="text-secondary mb-6">
        Abra um ticket explicando o motivo. A conversa fica neste chat e a equipe responde o mais
        breve possível.
      </p>
      <SupportInbox mode="customer" />
    </>
  );
}
