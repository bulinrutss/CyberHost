"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BusyLabel } from "@/components/PageLoader";
import { SvgChat, SvgPlus } from "@/components/ui/svgs";
import {
  api,
  type SupportStaff,
  type SupportTicket,
  type SupportTicketDetail,
  type User,
} from "@/lib/api";

type Props = {
  mode: "customer" | "admin";
};

const statusLabel: Record<string, string> = {
  open: "Aguardando",
  accepted: "Em atendimento",
  closed: "Encerrado",
};

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return (parts[0] || "?").slice(0, 2).toUpperCase();
}

function formatWhen(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const sameDay =
    date.getDate() === now.getDate() &&
    date.getMonth() === now.getMonth() &&
    date.getFullYear() === now.getFullYear();
  if (sameDay) {
    return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SupportInbox({ mode }: Props) {
  const isAdmin = mode === "admin";
  const [self, setSelf] = useState<User | null>(null);
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SupportTicketDetail | null>(null);
  const [staff, setStaff] = useState<SupportStaff[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [includeClosed, setIncludeClosed] = useState(false);
  const [subject, setSubject] = useState("");
  const [reason, setReason] = useState("");
  const [draft, setDraft] = useState("");
  const [mentionIds, setMentionIds] = useState<number[]>([]);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mobileChat, setMobileChat] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const selectedIdRef = useRef<number | null>(null);
  selectedIdRef.current = selectedId;

  const loadList = useCallback(async () => {
    const rows = isAdmin
      ? await api.adminSupportTickets(includeClosed)
      : await api.supportTickets();
    setTickets(rows);
    return rows;
  }, [isAdmin, includeClosed]);

  const loadDetail = useCallback(
    async (id: number) => {
      const item = isAdmin ? await api.adminSupportTicket(id) : await api.supportTicket(id);
      if (selectedIdRef.current === id) setDetail(item);
      return item;
    },
    [isAdmin]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await api.me();
        if (cancelled) return;
        setSelf(me);
        const rows = await loadList();
        if (cancelled) return;
        if (isAdmin) {
          const people = await api.adminSupportStaff();
          if (!cancelled) setStaff(people);
        }
        if (!selectedIdRef.current && rows.length === 1) {
          setSelectedId(rows[0].id);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Erro ao carregar suporte");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAdmin, loadList]);

  useEffect(() => {
    const timer = setInterval(() => {
      loadList().catch(() => undefined);
    }, 4000);
    return () => clearInterval(timer);
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    loadDetail(selectedId).catch((err) =>
      setError(err instanceof Error ? err.message : "Erro ao abrir ticket")
    );
    const timer = setInterval(() => {
      loadDetail(selectedId).catch(() => undefined);
    }, 2500);
    return () => clearInterval(timer);
  }, [selectedId, loadDetail]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [detail?.messages.length]);

  const openTicket = (id: number) => {
    setSelectedId(id);
    setCreating(false);
    setError("");
    setMobileChat(true);
    setDraft("");
    setMentionIds([]);
  };

  const submitNew = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const created = await api.supportCreateTicket({
        subject: subject.trim(),
        body: reason.trim(),
      });
      setSubject("");
      setReason("");
      setCreating(false);
      await loadList();
      openTicket(created.id);
      setDetail(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível abrir o ticket");
    } finally {
      setBusy(false);
    }
  };

  const sendDraft = async () => {
    if (!selectedId || !draft.trim()) return;
    setSending(true);
    setError("");
    try {
      const next = isAdmin
        ? await api.adminSupportSendMessage(selectedId, draft.trim(), mentionIds)
        : await api.supportSendMessage(selectedId, draft.trim());
      setDraft("");
      setMentionIds([]);
      setMentionOpen(false);
      setDetail(next);
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível enviar");
    } finally {
      setSending(false);
    }
  };

  const accept = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      const next = await api.adminSupportAccept(selectedId);
      setDetail(next);
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível aceitar");
    } finally {
      setBusy(false);
    }
  };

  const closeTicket = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      const next = isAdmin
        ? await api.adminSupportCloseTicket(selectedId)
        : await api.supportCloseTicket(selectedId);
      setDetail(next);
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível encerrar");
    } finally {
      setBusy(false);
    }
  };

  const deleteTicket = async () => {
    if (!selectedId || !isAdmin) return;
    if (!window.confirm("Apagar este ticket e todas as mensagens? Isso não tem volta.")) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.adminSupportDeleteTicket(selectedId);
      setSelectedId(null);
      setDetail(null);
      setMobileChat(false);
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível apagar o ticket");
    } finally {
      setBusy(false);
    }
  };

  const mentionable = useMemo(
    () => staff.filter((person) => person.id !== self?.id),
    [staff, self?.id]
  );

  const addMention = (person: SupportStaff) => {
    setMentionIds((current) => (current.includes(person.id) ? current : [...current, person.id]));
    setDraft((text) => {
      const replaced = text.replace(/@\S*$/, "");
      const prefix = replaced && !replaced.endsWith(" ") ? `${replaced} ` : replaced;
      return `${prefix}@${person.name.split(" ")[0]} `;
    });
    setMentionOpen(false);
  };

  const showList = !mobileChat || (!selectedId && !creating);

  return (
    <div className="glass-card overflow-hidden h-[min(78vh,820px)] min-h-[520px] flex">
      <aside
        className={`${
          showList ? "flex" : "hidden"
        } md:flex w-full md:w-[340px] shrink-0 flex-col border-r border-[var(--glass-border)] bg-[var(--bg-elevated)]/40`}
      >
        <div className="px-4 py-3 border-b border-[var(--glass-border)] flex items-center justify-between gap-2">
          <div>
            <p className="text-sm font-semibold">Tickets</p>
            <p className="text-xs text-muted">
              {isAdmin ? "Todos os administradores veem a fila" : "Seus pedidos de suporte"}
            </p>
          </div>
          {!isAdmin && (
            <button
              type="button"
              className="btn-primary !py-1.5 !px-3 text-sm"
              onClick={() => {
                setCreating(true);
                setSelectedId(null);
                setDetail(null);
                setMobileChat(true);
              }}
            >
              <span className="inline-flex items-center gap-1">
                <SvgPlus className="w-4 h-4" />
                Novo
              </span>
            </button>
          )}
        </div>
        {isAdmin && (
          <label className="px-4 py-2 text-xs text-muted flex items-center gap-2 border-b border-[var(--glass-border)]">
            <input
              type="checkbox"
              checked={includeClosed}
              onChange={(e) => setIncludeClosed(e.target.checked)}
            />
            Mostrar encerrados
          </label>
        )}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <p className="p-4 text-sm text-muted">Carregando conversas…</p>
          ) : tickets.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted">
              <SvgChat className="w-8 h-8 mx-auto mb-2 opacity-60" />
              {isAdmin ? "Nenhum ticket na fila." : "Você ainda não abriu um ticket."}
            </div>
          ) : (
            tickets.map((ticket) => {
              const active = ticket.id === selectedId;
              return (
                <button
                  key={ticket.id}
                  type="button"
                  onClick={() => openTicket(ticket.id)}
                  className={`w-full text-left px-4 py-3 flex gap-3 border-b border-[var(--glass-border)]/70 transition-colors ${
                    active ? "bg-[var(--accent)]/10" : "hover:bg-[var(--glass-bg)]"
                  }`}
                >
                  <span className="w-11 h-11 rounded-full bg-[var(--bg-base)] border border-[var(--glass-border)] flex items-center justify-center text-xs font-bold text-[var(--accent)] shrink-0">
                    {initials(isAdmin ? ticket.user_name : ticket.subject)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-medium truncate">
                        {isAdmin ? ticket.user_name : ticket.subject}
                      </span>
                      <span className="text-[11px] text-muted shrink-0">
                        {formatWhen(ticket.last_message_at)}
                      </span>
                    </span>
                    <span className="block text-xs text-muted truncate">
                      {isAdmin ? ticket.subject : ticket.last_message_preview}
                    </span>
                    <span className="mt-1 flex items-center gap-2">
                      <span
                        className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded-md border ${
                          ticket.status === "closed"
                            ? "text-muted border-[var(--glass-border)]"
                            : ticket.status === "accepted"
                              ? "text-emerald-400 border-emerald-500/30"
                              : "text-[var(--accent)] border-[var(--accent)]/30"
                        }`}
                      >
                        {statusLabel[ticket.status] ?? ticket.status}
                      </span>
                      {ticket.waiting_on_staff && ticket.status !== "closed" && (
                        <span className="w-2 h-2 rounded-full bg-[var(--accent)]" />
                      )}
                    </span>
                  </span>
                </button>
              );
            })
          )}
        </div>
      </aside>

      <section
        className={`${
          mobileChat || selectedId || creating ? "flex" : "hidden"
        } md:flex flex-1 min-w-0 flex-col bg-[var(--bg-base)]`}
      >
        {creating && !isAdmin ? (
          <form onSubmit={submitNew} className="flex flex-col h-full">
            <header className="px-4 py-3 border-b border-[var(--glass-border)] flex items-center gap-3">
              <button
                type="button"
                className="md:hidden btn-ghost !py-1 !px-2"
                onClick={() => {
                  setCreating(false);
                  setMobileChat(false);
                }}
              >
                Voltar
              </button>
              <div>
                <p className="font-semibold">Novo ticket</p>
                <p className="text-xs text-muted">Explique o motivo. Vamos responder o mais breve possível.</p>
              </div>
            </header>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <input
                required
                minLength={3}
                maxLength={80}
                placeholder="Assunto"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="input-glass"
              />
              <textarea
                required
                minLength={3}
                maxLength={4000}
                rows={8}
                placeholder="Descreva o que aconteceu, o serviço e o que você já tentou."
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="input-glass min-h-[180px]"
              />
              {error && <p className="text-sm text-red-400">{error}</p>}
            </div>
            <div className="p-4 border-t border-[var(--glass-border)]">
              <button type="submit" disabled={busy} className="btn-primary w-full">
                {busy ? <BusyLabel>Abrindo ticket…</BusyLabel> : "Abrir ticket"}
              </button>
            </div>
          </form>
        ) : detail ? (
          <>
            <header className="px-4 py-3 border-b border-[var(--glass-border)] flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="md:hidden btn-ghost !py-1 !px-2"
                    onClick={() => {
                      setMobileChat(false);
                      setSelectedId(null);
                    }}
                  >
                    Voltar
                  </button>
                  <p className="font-semibold truncate">
                    {isAdmin ? detail.user_name : detail.subject}
                  </p>
                </div>
                <p className="text-xs text-muted truncate">
                  {isAdmin ? detail.subject : "A equipe responde o mais breve possível."}
                  {detail.accepted_by_name ? ` · ${detail.accepted_by_name} em atendimento` : ""}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 shrink-0">
                {isAdmin && detail.status !== "closed" && detail.accepted_by_id !== self?.id && (
                  <button type="button" className="btn-primary !py-1.5 !px-3 text-sm" onClick={accept} disabled={busy}>
                    {detail.accepted_by_id ? "Assumir atendimento" : "Aceitar atendimento"}
                  </button>
                )}
                {detail.status !== "closed" && (
                  <button type="button" className="btn-ghost !py-1.5 !px-3 text-sm" onClick={closeTicket} disabled={busy}>
                    Encerrar
                  </button>
                )}
                {isAdmin && (
                  <button
                    type="button"
                    className="btn-ghost !py-1.5 !px-3 text-sm !text-[var(--danger)] !border-[var(--danger)]/30 hover:!bg-[var(--danger)]/10"
                    onClick={() => void deleteTicket()}
                    disabled={busy}
                  >
                    {busy ? "…" : "Apagar"}
                  </button>
                )}
              </div>
            </header>
            {error ? <p className="px-4 pt-2 text-sm text-red-400">{error}</p> : null}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-[radial-gradient(circle_at_top,rgba(6,201,108,0.06),transparent_42%)]">
              {detail.messages.map((message) => {
                if (message.is_system) {
                  return (
                    <p key={message.id} className="text-center text-xs text-muted py-1">
                      {message.body}
                    </p>
                  );
                }
                const mine = message.author_id === self?.id;
                return (
                  <div key={message.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm shadow-sm ${
                        mine
                          ? "bg-[var(--accent)] text-black rounded-br-md"
                          : "bg-[var(--bg-elevated)] border border-[var(--glass-border)] rounded-bl-md"
                      }`}
                    >
                      {!mine && (
                        <p className={`text-[11px] font-semibold mb-0.5 ${mine ? "" : "text-[var(--accent)]"}`}>
                          {message.author_name}
                        </p>
                      )}
                      <p className="whitespace-pre-wrap break-words">{message.body}</p>
                      <p className={`text-[10px] mt-1 ${mine ? "text-black/60" : "text-muted"}`}>
                        {formatWhen(message.created_at)}
                      </p>
                    </div>
                  </div>
                );
              })}
              <div ref={bottomRef} />
            </div>
            {detail.status === "closed" ? (
              <p className="px-4 py-3 text-sm text-muted border-t border-[var(--glass-border)]">
                Este ticket foi encerrado.
              </p>
            ) : (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void sendDraft();
                }}
                className="p-3 border-t border-[var(--glass-border)] space-y-2"
              >
                {isAdmin && mentionIds.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {mentionIds.map((id) => {
                      const person = staff.find((item) => item.id === id);
                      if (!person) return null;
                      return (
                        <button
                          key={id}
                          type="button"
                          className="text-xs px-2 py-1 rounded-full bg-[var(--accent)]/15 text-[var(--accent)]"
                          onClick={() => setMentionIds((current) => current.filter((item) => item !== id))}
                        >
                          @{person.name.split(" ")[0]} ×
                        </button>
                      );
                    })}
                  </div>
                )}
                {error && <p className="text-sm text-red-400">{error}</p>}
                <div className="flex gap-2 items-end">
                  {isAdmin && (
                    <div className="relative">
                      <button
                        type="button"
                        className="btn-ghost !py-2 !px-3"
                        onClick={() => setMentionOpen((open) => !open)}
                      >
                        @
                      </button>
                      {mentionOpen && (
                        <div className="absolute bottom-full left-0 mb-2 w-56 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-base)] shadow-xl z-20 max-h-48 overflow-y-auto">
                          {mentionable.length === 0 ? (
                            <p className="p-3 text-xs text-muted">Nenhum outro admin.</p>
                          ) : (
                            mentionable.map((person) => (
                              <button
                                key={person.id}
                                type="button"
                                className="w-full text-left px-3 py-2 text-sm hover:bg-[var(--glass-bg)]"
                                onClick={() => addMention(person)}
                              >
                                {person.name}
                              </button>
                            ))
                          )}
                        </div>
                      )}
                    </div>
                  )}
                  <textarea
                    rows={2}
                    maxLength={4000}
                    value={draft}
                    onChange={(e) => {
                      const value = e.target.value;
                      setDraft(value);
                      if (isAdmin) setMentionOpen(/@\S*$/.test(value));
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void sendDraft();
                      }
                    }}
                    placeholder={isAdmin ? "Mensagem. Use @ para mencionar outro admin." : "Escreva sua mensagem"}
                    className="input-glass flex-1 !py-2 min-h-[44px] max-h-32"
                  />
                  <button type="submit" disabled={sending || !draft.trim()} className="btn-primary !py-2">
                    {sending ? "…" : "Enviar"}
                  </button>
                </div>
              </form>
            )}
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 text-muted">
            <SvgChat className="w-12 h-12 mb-3 opacity-50" />
            <p className="font-medium text-[var(--text-primary)] mb-1">
              {isAdmin ? "Selecione um ticket" : "Fale com o suporte"}
            </p>
            <p className="text-sm max-w-sm">
              {isAdmin
                ? "A fila fica visível para todos os administradores. Aceite ou assuma um atendimento a qualquer momento."
                : "Abra um ticket com o motivo. A equipe responde o mais breve possível por este chat."}
            </p>
            {!isAdmin && (
              <button
                type="button"
                className="btn-primary mt-4"
                onClick={() => {
                  setCreating(true);
                  setMobileChat(true);
                }}
              >
                Abrir ticket
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
