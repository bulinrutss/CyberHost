"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type WebPageConfig,
  type WebPageEditor,
  type WebPageLink,
  type WebPageTemplate,
  type WebSite,
} from "@/lib/api";
import { WebPageLinkIcon } from "@/components/webPageIcons";

type Props = {
  site: WebSite;
  admin?: boolean;
};

function newLink(): WebPageLink {
  return {
    id: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `link-${Date.now()}`,
    label: "Novo link",
    url: "https://",
    icon: null,
  };
}

function defaultConfig(template: WebPageTemplate): WebPageConfig {
  return {
    template_id: template.id,
    title: "",
    subtitle: "",
    avatar_path: null,
    accent_color: template.preview_accent,
    background_color: template.preview_background,
    text_color: template.id === "sunset" ? "#fff7ed" : "#e2e8f0",
    links: [newLink()],
  };
}

export function WebPageBuilderPanel({ site, admin = false }: Props) {
  const [editor, setEditor] = useState<WebPageEditor | null>(null);
  const [config, setConfig] = useState<WebPageConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = admin ? await api.adminWebSitePageEditor(site.id) : await api.webSitePageEditor(site.id);
      setEditor(data);
      if (data.config) {
        setConfig(data.config);
      } else if (data.templates[0]) {
        setConfig(defaultConfig(data.templates[0]));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível carregar o criador");
    } finally {
      setLoading(false);
    }
  }, [admin, site.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectTemplate = (template: WebPageTemplate) => {
    setConfig((current) => ({
      ...defaultConfig(template),
      title: current?.title ?? "",
      subtitle: current?.subtitle ?? "",
      links: current?.links?.length ? current.links : [newLink()],
      avatar_path: current?.avatar_path ?? null,
    }));
  };

  const updateLink = (id: string, patch: Partial<WebPageLink>) => {
    setConfig((current) =>
      current
        ? {
            ...current,
            links: current.links.map((link) => (link.id === id ? { ...link, ...patch } : link)),
          }
        : current
    );
  };

  const addLink = () => {
    setConfig((current) => (current ? { ...current, links: [...current.links, newLink()] } : current));
  };

  const removeLink = (id: string) => {
    setConfig((current) =>
      current ? { ...current, links: current.links.filter((link) => link.id !== id) } : current
    );
  };

  const save = async () => {
    if (!config) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const data = admin
        ? await api.adminSaveWebSitePage(site.id, config)
        : await api.saveWebSitePage(site.id, config);
      setEditor(data);
      setConfig(data.config ?? config);
      setNotice("Página publicada! Abra o link do site para ver.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setSaving(false);
    }
  };

  const uploadAvatar = async (file: File | null) => {
    if (!file) return;
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const data = admin
        ? await api.adminUploadWebSitePageAvatar(site.id, file)
        : await api.uploadWebSitePageAvatar(site.id, file);
      setEditor(data);
      if (data.config) setConfig(data.config);
      setNotice("Foto atualizada.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível enviar a imagem");
    } finally {
      setUploading(false);
    }
  };

  if (loading || !editor || !config) {
    return <div className="glass-card p-8 shimmer h-48 rounded-2xl" />;
  }

  const avatarUrl = editor.avatar_url;

  return (
    <div className="space-y-6">
      {error ? (
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-sm text-red-400">{error}</div>
      ) : null}
      {notice ? (
        <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-400">
          {notice}
        </div>
      ) : null}

      <div className="glass-card p-6 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold">Modelos gratuitos</h3>
            <p className="text-sm text-secondary mt-1">
              Escolha um visual estilo Linktree. Depois personalize textos, cores e links.
            </p>
          </div>
          <a
            href={site.public_url}
            target="_blank"
            rel="noreferrer"
            className="btn-ghost text-xs !py-1.5 !px-3"
          >
            Ver site ao vivo
          </a>
        </div>
        <div className="grid sm:grid-cols-3 gap-3">
          {editor.templates.map((template) => {
            const active = config.template_id === template.id;
            return (
              <button
                key={template.id}
                type="button"
                onClick={() => selectTemplate(template)}
                className={`rounded-xl border p-4 text-left transition ${
                  active
                    ? "border-[var(--accent)] bg-[var(--accent)]/10"
                    : "border-[var(--glass-border)] hover:border-[var(--accent)]/40"
                }`}
              >
                <div
                  className="h-20 rounded-lg mb-3 border border-white/10"
                  style={{
                    background: `linear-gradient(160deg, ${template.preview_background}, ${template.preview_accent}55)`,
                  }}
                />
                <p className="font-medium text-sm">{template.name}</p>
                <p className="text-xs text-muted mt-1 leading-relaxed">{template.description}</p>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="glass-card p-6 space-y-4">
          <h3 className="font-semibold">Conteúdo</h3>

          <div className="flex items-center gap-4">
            <div
              className="w-20 h-20 rounded-full border border-[var(--glass-border)] overflow-hidden bg-[var(--bg-elevated)] flex items-center justify-center text-2xl font-bold text-[var(--accent)]"
            >
              {avatarUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
              ) : (
                (config.title || "?").slice(0, 1).toUpperCase()
              )}
            </div>
            <div>
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                className="hidden"
                onChange={(e) => void uploadAvatar(e.target.files?.[0] ?? null)}
              />
              <button
                type="button"
                disabled={uploading}
                onClick={() => fileRef.current?.click()}
                className="btn-ghost text-xs !py-1.5 !px-3"
              >
                {uploading ? "Enviando…" : "Enviar foto"}
              </button>
              <p className="text-xs text-muted mt-1">JPG, PNG, WebP ou GIF · até 2 MB</p>
            </div>
          </div>

          <label className="block text-sm">
            <span className="text-muted">Título</span>
            <input
              value={config.title}
              onChange={(e) => setConfig({ ...config, title: e.target.value })}
              className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)]"
              placeholder="Seu nome ou marca"
            />
          </label>

          <label className="block text-sm">
            <span className="text-muted">Subtítulo / bio</span>
            <textarea
              value={config.subtitle}
              onChange={(e) => setConfig({ ...config, subtitle: e.target.value })}
              rows={3}
              className="mt-1 w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] resize-y"
              placeholder="Uma frase sobre você"
            />
          </label>

          <div className="grid grid-cols-3 gap-3">
            <label className="text-xs">
              Destaque
              <input
                type="color"
                value={config.accent_color}
                onChange={(e) => setConfig({ ...config, accent_color: e.target.value })}
                className="mt-1 w-full h-10 rounded-lg border border-[var(--glass-border)] bg-transparent cursor-pointer"
              />
            </label>
            <label className="text-xs">
              Fundo
              <input
                type="color"
                value={config.background_color}
                onChange={(e) => setConfig({ ...config, background_color: e.target.value })}
                className="mt-1 w-full h-10 rounded-lg border border-[var(--glass-border)] bg-transparent cursor-pointer"
              />
            </label>
            <label className="text-xs">
              Texto
              <input
                type="color"
                value={config.text_color}
                onChange={(e) => setConfig({ ...config, text_color: e.target.value })}
                className="mt-1 w-full h-10 rounded-lg border border-[var(--glass-border)] bg-transparent cursor-pointer"
              />
            </label>
          </div>
        </div>

        <div className="glass-card p-6 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-semibold">Links</h3>
            <button type="button" onClick={addLink} className="btn-ghost text-xs !py-1.5 !px-3">
              + Adicionar
            </button>
          </div>

          <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
            {config.links.length === 0 ? (
              <p className="text-sm text-muted">Nenhum link ainda.</p>
            ) : (
              config.links.map((link, index) => (
                <div key={link.id} className="rounded-xl border border-[var(--glass-border)] p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs text-muted">Link {index + 1}</span>
                    <button
                      type="button"
                      onClick={() => removeLink(link.id)}
                      className="text-xs text-[var(--danger)] hover:underline"
                    >
                      Remover
                    </button>
                  </div>
                  <input
                    value={link.label}
                    onChange={(e) => updateLink(link.id, { label: e.target.value })}
                    placeholder="Texto do botão"
                    className="w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] text-sm"
                  />
                  <div>
                    <p className="text-xs text-muted mb-2">Ícone (opcional)</p>
                    <div className="flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        title="Sem ícone"
                        onClick={() => updateLink(link.id, { icon: null })}
                        className={`w-9 h-9 rounded-lg border flex items-center justify-center text-xs ${
                          !link.icon
                            ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                            : "border-[var(--glass-border)] text-muted hover:border-[var(--accent)]/40"
                        }`}
                      >
                        —
                      </button>
                      {(editor.link_icons ?? []).map((icon) => (
                        <button
                          key={icon.id}
                          type="button"
                          title={icon.label}
                          onClick={() => updateLink(link.id, { icon: icon.id })}
                          className={`w-9 h-9 rounded-lg border flex items-center justify-center ${
                            link.icon === icon.id
                              ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                              : "border-[var(--glass-border)] text-[var(--text-secondary)] hover:border-[var(--accent)]/40"
                          }`}
                        >
                          <WebPageLinkIcon id={icon.id} className="w-4 h-4" />
                        </button>
                      ))}
                    </div>
                  </div>
                  <input
                    value={link.url}
                    onChange={(e) => updateLink(link.id, { url: e.target.value })}
                    placeholder="https://"
                    className="w-full px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--bg-elevated)] text-sm font-mono"
                  />
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <button type="button" disabled={saving} onClick={() => void save()} className="btn-primary">
          {saving ? "Publicando…" : editor.using_builder ? "Salvar e publicar" : "Criar página"}
        </button>
        <p className="text-xs text-muted self-center">
          Gera o <code className="text-[var(--accent)]">index.html</code> do seu site automaticamente.
        </p>
      </div>
    </div>
  );
}
