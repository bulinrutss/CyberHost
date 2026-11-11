type Props = {
  dnsTarget: string;
  compact?: boolean;
};

function isIpv4(value: string): boolean {
  return /^\d{1,3}(\.\d{1,3}){3}$/.test(value.trim());
}

function HttpsPropagationNotice() {
  return (
    <p className="text-xs text-muted leading-relaxed">
      <strong className="text-[var(--text-secondary)]">HTTPS automático:</strong> depois que o DNS propagar e você
      salvar o domínio, o certificado é emitido em alguns minutos.{" "}
      <strong className="text-[var(--text-secondary)]">Enquanto isso, o site fica em HTTP</strong> — não precisa
      configurar nada extra no DNS.
    </p>
  );
}

export function WebDomainDnsHint({ dnsTarget, compact = false }: Props) {
  if (!dnsTarget) return null;

  const useCname = !isIpv4(dnsTarget);

  if (compact) {
    return (
      <div className="mt-2 space-y-1.5">
        <p className="text-xs text-muted leading-relaxed">
          {useCname ? (
            <>
              No DNS do seu domínio, crie um registro{" "}
              <strong className="text-[var(--text-secondary)]">CNAME</strong> para o subdomínio do site (ex.:{" "}
              <code className="text-[var(--accent)]">loja</code>) apontando para{" "}
              <code className="text-[var(--accent)]">{dnsTarget}</code>. No domínio raiz (
              <code className="text-[var(--accent)]">@</code>), use registro <strong>A</strong> com o mesmo destino
              de <code className="text-[var(--accent)]">{dnsTarget}</code> (ou ALIAS/ANAME, se o provedor oferecer).
              Repita para <code className="text-[var(--accent)]">www</code> se quiser o endereço com www.
            </>
          ) : (
            <>
              No DNS do seu domínio, crie um registro <strong className="text-[var(--text-secondary)]">A</strong>{" "}
              para o nome do site (ex.: <code className="text-[var(--accent)]">loja</code> ou{" "}
              <code className="text-[var(--accent)]">@</code>) apontando para{" "}
              <code className="text-[var(--accent)]">{dnsTarget}</code>. Repita para{" "}
              <code className="text-[var(--accent)]">www</code> se quiser o endereço com www.
            </>
          )}{" "}
          Depois salve o domínio aqui e aguarde a propagação do DNS.
        </p>
        <HttpsPropagationNotice />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]/60 p-4 text-sm text-[var(--text-secondary)] space-y-2">
      <p className="font-semibold text-[var(--text-primary)]">Como apontar o DNS</p>
      <ol className="list-decimal list-inside space-y-1.5 text-xs leading-relaxed">
        <li>
          No painel do seu domínio (Registro.br, Cloudflare, etc.), abra a zona DNS do domínio.
        </li>
        {useCname ? (
          <>
            <li>
              Para subdomínio (ex.: <code>loja</code>), crie um registro <strong>CNAME</strong> apontando para{" "}
              <code className="text-[var(--accent)]">{dnsTarget}</code>.
            </li>
            <li>
              Para o domínio raiz (<code>@</code>), use registro <strong>A</strong> com o mesmo destino de{" "}
              <code className="text-[var(--accent)]">{dnsTarget}</code> ou ALIAS/ANAME, se disponível.
            </li>
            <li>
              Para <code>www.seudominio.com</code>, use <strong>CNAME</strong> com nome <code>www</code> para{" "}
              <code className="text-[var(--accent)]">{dnsTarget}</code>.
            </li>
          </>
        ) : (
          <>
            <li>
              Crie um registro <strong>A</strong> com o nome do subdomínio (ex.: <code>loja</code>) ou{" "}
              <code>@</code> para o domínio raiz, apontando para{" "}
              <code className="text-[var(--accent)]">{dnsTarget}</code>.
            </li>
            <li>
              Para <code>www.seudominio.com</code>, crie outro registro <strong>A</strong> com nome{" "}
              <code>www</code> para o mesmo IP.
            </li>
          </>
        )}
        <li>Cadastre aqui o domínio completo (ex.: <code>loja.seudominio.com.br</code>).</li>
        <li>A propagação do DNS pode levar de alguns minutos a algumas horas.</li>
      </ol>
      <HttpsPropagationNotice />
    </div>
  );
}
