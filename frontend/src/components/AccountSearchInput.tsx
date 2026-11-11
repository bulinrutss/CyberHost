"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { type User } from "@/lib/api";
import { formatPhoneDisplay } from "@/lib/phone";

export function accountMatches(user: User, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const digits = q.replace(/\D/g, "");
  if (user.name.toLowerCase().includes(q)) return true;
  if ((user.email || "").toLowerCase().includes(q)) return true;
  if (user.phone.includes(q) || formatPhoneDisplay(user.phone).toLowerCase().includes(q)) return true;
  if (digits.length >= 3 && user.phone.includes(digits)) return true;
  if (String(user.id) === q) return true;
  return false;
}

export function AccountSearchInput({
  users,
  selectedId,
  onSelect,
  activeOnly = true,
}: {
  users: User[];
  selectedId: number | null;
  onSelect: (user: User | null) => void;
  activeOnly?: boolean;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const selected = users.find((u) => u.id === selectedId) || null;

  const matches = useMemo(() => {
    const filtered = users.filter((u) => (!activeOnly || u.is_active) && accountMatches(u, query));
    return filtered.slice(0, 12);
  }, [users, query, activeOnly]);

  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  if (selected) {
    return (
      <div className="flex items-start gap-2 min-w-[240px]">
        <div className="min-w-0 flex-1">
          <p className="font-medium truncate">{selected.name}</p>
          <p className="text-xs text-muted truncate">{formatPhoneDisplay(selected.phone)}</p>
          {selected.email ? <p className="text-xs text-muted truncate">{selected.email}</p> : null}
        </div>
        <button
          type="button"
          className="text-xs text-muted hover:text-[var(--danger)] shrink-0"
          onClick={() => onSelect(null)}
        >
          Trocar
        </button>
      </div>
    );
  }

  return (
    <div ref={wrapRef} className="relative min-w-[240px]">
      <input
        type="search"
        autoComplete="off"
        placeholder="Buscar nome, telefone ou e-mail"
        className="input-glass !py-1.5 !text-sm w-full"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
      />
      {open && (
        <ul className="absolute z-30 left-0 right-0 mt-1 max-h-56 overflow-y-auto rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] shadow-lg">
          {matches.length === 0 ? (
            <li className="px-3 py-2 text-xs text-muted">Nenhuma conta encontrada</li>
          ) : (
            matches.map((user) => (
              <li key={user.id}>
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 hover:bg-[var(--glass-border)]/40"
                  onClick={() => {
                    onSelect(user);
                    setQuery("");
                    setOpen(false);
                  }}
                >
                  <span className="block text-sm font-medium truncate">{user.name}</span>
                  <span className="block text-xs text-muted truncate">
                    {formatPhoneDisplay(user.phone)}
                    {user.email ? ` · ${user.email}` : ""}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
