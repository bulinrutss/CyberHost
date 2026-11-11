"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PageShell } from "@/components/ui/PageShell";
import { BusyLabel } from "@/components/PageLoader";
import { api, getToken, type PixDevItem } from "@/lib/api";

function kindLabel(kind: string | null) {
  if (kind === "vps") return "VPS";
  if (kind === "game") return "Game";
  if (kind === "cloud") return "CyberCloud";
  return kind || "—";
}

function resultClass(item: PixDevItem) {
  if (item.action === "released") return "border-green-800 bg-green-400/10 text-green-400";
  if (item.action === "already") return "border-[var(--glass-border)] text-secondary";
  return "border-red-800 bg-red-400/10 text-red-400";
}

export default function PixDevPage() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<PixDevItem[] | null>(null);
  const [summary, setSummary] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api
      .me()
      .then((user) => {
        if (!user.is_admin) router.replace("/dashboard");
      })
      .catch(() => router.push("/login"));
  }, [router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSummary("");
    setResults(null);
    setLoading(true);
    try {
      const response = await api.adminPixdevRelease(text);
      setResults(response.results);
      const parts = [
        response.released ? `${response.released} liberado(s)` : "",
        response.skipped ? `${response.skipped} já estava(m) pago(s)` : "",
        response.failed ? `${response.failed} falhou(aram)` : "",
      ].filter(Boolean);
      setSummary(parts.join(" · ") || "Nada processado");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao liberar Pix");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageShell admin>
      <Link href="/admin" className="text-sm text-muted hover:text-[var(--accent)] mb-6 inline-block">
        ← Painel admin
      </Link>
      <p className="text-sm text-[var(--accent)] uppercase tracking-wide mb-2">Administração</p>
      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">Pix DevMode</h1>
      <p className="text-secondary mb-8 max-w-2xl">
        Cole o código copia-e-cola do QR, o link ou o id <code className="text-[var(--accent)]">pix_char_</code>.
        Se o QR não tiver o id no texto, o pedido é encontrado pelo próprio código Pix. Em seguida a página simula o pagamento sandbox e libera como pago.
      </p>

      <form onSubmit={submit} className="glass-card p-6 space-y-4 max-w-3xl">
        <label htmlFor="pixdev-text" className="block text-sm font-medium">
          Códigos Pix
        </label>
        <textarea
          id="pixdev-text"
          required
          minLength={8}
          rows={10}
          spellCheck={false}
          autoComplete="off"
          placeholder={"Cole um ou mais pix_char_, BR Code ou URL — um por linha"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="input-glass font-mono text-xs min-h-[180px] resize-y"
        />
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? <BusyLabel>Liberando…</BusyLabel> : "Liberar como pago"}
          </button>
          <button
            type="button"
            className="btn-ghost"
            disabled={loading || !text}
            onClick={() => {
              setText("");
              setResults(null);
              setSummary("");
              setError("");
            }}
          >
            Limpar
          </button>
        </div>
      </form>

      {error && (
        <p className="text-red-400 text-sm bg-red-400/10 border border-red-800 rounded-xl px-4 py-3 mt-6">
          {error}
        </p>
      )}
      {summary && (
        <p className="text-secondary text-sm mt-6">{summary}</p>
      )}
      {results && results.length > 0 && (
        <ul className="mt-4 space-y-3 max-w-3xl">
          {results.map((item) => (
            <li
              key={item.charge_id}
              className={`rounded-xl border px-4 py-3 text-sm ${resultClass(item)}`}
            >
              <p className="font-mono break-all">{item.charge_id}</p>
              <p className="mt-1">
                {item.detail}
                {item.simulated ? " · simulado" : ""}
              </p>
              <p className="mt-1 text-xs opacity-80">
                {kindLabel(item.kind)}
                {item.order_id != null ? ` · pedido ${item.order_id}` : ""}
                {item.order_status ? ` · ${item.order_status}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
