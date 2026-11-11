import Image from "next/image";
import Link from "next/link";
import { MarketingFooter } from "@/components/MarketingFooter";
import { MarketingNavbar } from "@/components/MarketingNavbar";
import { VpsPriceSimulator } from "@/components/VpsPriceSimulator";
import { publicAsset } from "@/lib/publicAsset";
import { GAME_HOSTING_ENABLED, WEB_HOSTING_ENABLED } from "@/lib/features";
import {
  SvgArrowRight,
  SvgBolt,
  SvgCloud,
  SvgDisk,
  SvgHeadphones,
  SvgMemory,
  SvgRocket,
  SvgServer,
  SvgShield,
  SvgTrendingUp,
} from "@/components/ui/svgs";

const features = [
  {
    svg: SvgCloud,
    title: "CyberCloud incluído",
    desc: "20 GB de armazenamento na nuvem em toda conta. Cada VPS ativa soma espaço extra — e você pode contratar mais a qualquer momento.",
  },
  {
    svg: SvgServer,
    title: "Servidores Dedicados",
    desc: "Hardware físico totalmente dedicado com a melhor velocidade e desempenho do mercado para suas aplicações críticas.",
  },
  {
    svg: SvgTrendingUp,
    title: "Escalabilidade Inteligente",
    desc: "Sua aplicação online em minutos e totalmente escalável. Ajuste recursos a qualquer momento sem perda de dados.",
  },
  {
    svg: SvgHeadphones,
    title: "Suporte Especializado",
    desc: "Atendimento 24/7 com especialistas em infraestrutura. Resposta rápida para manter seus serviços sempre online.",
  },
];

const technologies = [
  { src: "/fivem.webp", name: "FiveM" },
  { src: "/mine.webp", name: "Minecraft" },
  { src: "/mtasa.webp", name: "MTA:SA" },
  { src: "/rust.png", name: "Rust" },
  { src: "/dayz.png", name: "DayZ" },
];

export default function HomePage() {
  return (
    <div className="marketing-page">
      <MarketingNavbar />

      <section id="inicio" className="marketing-hero-bg pt-12 pb-20 sm:pt-16 sm:pb-28">
        <div className="max-w-cyber mx-auto px-4 sm:px-6">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
            <div>
              <div className="hero-badge mb-6">
                <SvgShield className="w-4 h-4 shrink-0" />
                Líder em Hospedagem VPS no Brasil
              </div>

              <h1 className="text-4xl sm:text-5xl lg:text-[3.25rem] font-extrabold leading-[1.15] tracking-tight mb-6">
                Hospedagem VPS de{" "}
                <span className="gradient-text">Alta Performance</span> para suas Aplicações
              </h1>

              <p className="text-lg text-[var(--text-secondary)] leading-relaxed mb-8 max-w-xl">
                Infraestrutura empresarial com NVMe, processadores Xeon, uptime de 99.9%
                e suporte técnico especializado 24/7. Toda conta inclui{" "}
                <span className="font-medium text-[var(--text-primary)]">20 GB no CyberCloud</span> —
                e cada VPS ativa aumenta seu espaço na nuvem.
              </p>

              <div className="grid grid-cols-3 gap-4 mb-10">
                {[
                  { n: "99.9%", l: "Uptime Garantido" },
                  { n: "24/7", l: "Suporte Técnico" },
                  { n: "300MB/s", l: "Conexão Dedicada" },
                ].map((s) => (
                  <div key={s.l}>
                    <div className="stat-number">{s.n}</div>
                    <div className="text-xs sm:text-sm text-[var(--text-muted)] mt-1">{s.l}</div>
                  </div>
                ))}
              </div>

              <div className="flex flex-col sm:flex-row gap-4">
                <Link href="#planos" className="btn-primary !px-8 !py-3.5 text-base">
                  <SvgRocket className="w-4 h-4" />
                  Simular preços
                </Link>
                <Link href="/login" className="btn-ghost-marketing !px-8 !py-3.5 text-base">
                  <SvgCloud className="w-4 h-4" />
                  Acessar painel
                </Link>
              </div>
            </div>

            <div className="relative flex justify-center lg:justify-end">
              <div className="relative w-full max-w-md">
                <Image
                  src={publicAsset("/server.png")}
                  alt="Servidor VPS"
                  width={420}
                  height={420}
                  className="w-full h-auto drop-shadow-2xl animate-float-slow"
                  priority
                />
                <div className="float-badge top-8 -left-2 sm:left-0 animate-float-slow" style={{ animationDelay: "0s" }}>
                  <SvgDisk className="w-4 h-4 shrink-0" />
                  NVMe SSD
                </div>
                <div className="float-badge top-1/3 -right-2 sm:right-0 animate-float-slow" style={{ animationDelay: "0.5s" }}>
                  <SvgBolt className="w-4 h-4 shrink-0" />
                  Xeon CPU
                </div>
                <div className="float-badge bottom-16 left-4 animate-float-slow" style={{ animationDelay: "1s" }}>
                  <SvgMemory className="w-4 h-4 shrink-0" />
                  DDR4 RAM
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {WEB_HOSTING_ENABLED && (
      <section id="web-hosting" className="py-20 sm:py-24 border-b border-[var(--glass-border)]">
        <div className="max-w-cyber mx-auto px-4 sm:px-6">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <p className="text-sm font-semibold text-[var(--accent)] uppercase tracking-wide mb-3">
                Novo — Sites
              </p>
              <h2 className="text-3xl sm:text-4xl font-bold mb-4">
                Seu site no ar em minutos
              </h2>
              <p className="text-[var(--text-secondary)] leading-relaxed mb-6">
                Publique HTML ou PHP sem VPS. Ao contratar, você já recebe um{" "}
                <strong className="text-[var(--text-primary)]">link personalizado</strong>, online e público. Se
                preferir, conecte seu próprio domínio depois — fácil, em poucos cliques no painel.
              </p>
              <ul className="space-y-3 text-sm text-[var(--text-secondary)] mb-8">
                <li className="flex gap-2">
                  <span className="text-[var(--accent)]">✓</span>
                  Planos a partir de R$ 2,99/mês
                </li>
                <li className="flex gap-2">
                  <span className="text-[var(--accent)]">✓</span>
                  Link personalizado na hora — sem configurar DNS
                </li>
                <li className="flex gap-2">
                  <span className="text-[var(--accent)]">✓</span>
                  PHP no plano Pro
                </li>
                <li className="flex gap-2">
                  <span className="text-[var(--accent)]">✓</span>
                  Domínio próprio e HTTPS quando quiser
                </li>
              </ul>
              <div className="flex flex-col sm:flex-row gap-3">
                <Link href="/order/web" className="btn-primary !px-6">
                  Contratar site
                </Link>
                <Link href="#planos" className="btn-ghost-marketing !px-6">
                  Ver VPS Windows
                </Link>
              </div>
            </div>
            <div className="glass-card p-8 space-y-4 text-sm">
              <h3 className="font-bold text-lg">Starter · Plus · Pro</h3>
              <p className="text-[var(--text-secondary)]">
                Starter (256 MB RAM, HTML/CSS/JS), Plus (512 MB RAM, HTML/CSS/JS) e Pro (2 GB de espaço, PHP). Depois de
                contratar, envie os arquivos pela pasta <code>public</code>.
              </p>
            </div>
          </div>
        </div>
      </section>
      )}

      {GAME_HOSTING_ENABLED && (
      <section id="game-hosting" className="py-20 sm:py-24 border-b border-[var(--glass-border)]">
        <div className="max-w-cyber mx-auto px-4 sm:px-6">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <p className="text-sm font-semibold text-[var(--accent)] uppercase tracking-wide mb-3">
                Novo — Game Hosting
              </p>
              <h2 className="text-3xl sm:text-4xl font-bold mb-4">
                Servidores de jogo prontos para usar
              </h2>
              <p className="text-[var(--text-secondary)] leading-relaxed mb-6">
                Para <strong className="text-[var(--text-primary)]">SA-MP</strong>,{" "}
                <strong className="text-[var(--text-primary)]">MTA:SA</strong>,{" "}
                <strong className="text-[var(--text-primary)]">Minecraft</strong> e{" "}
                <strong className="text-[var(--text-primary)]">FiveM</strong>, oferecemos uma
                hospedagem diferente da VPS: você recebe uma pasta de arquivos do servidor, com
                botões de iniciar, parar e reiniciar — sem precisar administrar Windows ou RDP.
              </p>
              <ul className="space-y-3 text-sm text-[var(--text-secondary)] mb-8">
                <li className="flex gap-2">
                  <span className="text-[var(--accent)]">✓</span>
                  Painel com arquivos (server.cfg, gamemodes, mods)
                </li>
                <li className="flex gap-2">
                  <span className="text-[var(--accent)]">✓</span>
                  Start / Stop / Restart em um clique
                </li>
                <li className="flex gap-2">
                  <span className="text-[var(--accent)]">✓</span>
                  Logs do servidor em tempo real
                </li>
                <li className="flex gap-2">
                  <span className="text-[var(--accent)]">✓</span>
                  Planos a partir de R$ 19,90/mês
                </li>
              </ul>
              <div className="flex flex-col sm:flex-row gap-3">
                <Link href="/order/game" className="btn-primary !px-6">
                  Contratar servidor de jogo
                </Link>
                <Link href="#planos" className="btn-ghost-marketing !px-6">
                  Ver VPS Windows
                </Link>
              </div>
            </div>

            <div className="glass-card p-8 space-y-6">
              <h3 className="font-bold text-lg">VPS vs Game Hosting — qual escolher?</h3>
              <div className="space-y-4 text-sm">
                <div className="p-4 rounded-xl bg-[var(--bg-elevated)] border border-[var(--glass-border)]">
                  <p className="font-semibold mb-1">VPS Windows</p>
                  <p className="text-[var(--text-secondary)]">
                    Máquina virtual completa com RDP. Ideal para aplicações customizadas,
                    múltiplos serviços ou quando você precisa de controle total do SO.
                  </p>
                </div>
                <div className="p-4 rounded-xl bg-[var(--accent)]/5 border border-[var(--accent)]/30">
                  <p className="font-semibold mb-1 text-[var(--accent)]">Game Hosting</p>
                  <p className="text-[var(--text-secondary)]">
                    Hospedagem em host Linux — só a pasta do jogo (FXServer, SAMP, MTA, etc.).
                    Mais barato e simples: edite arquivos, resources e ligue o servidor no painel.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      )}

      <section id="planos" className="py-20 sm:py-24 bg-[var(--bg-elevated)]">
        <div className="max-w-cyber mx-auto px-4 sm:px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">Simule o valor da sua VPS</h2>
            <p className="text-[var(--text-secondary)] max-w-2xl mx-auto">
              Planos predefinidos ou configuração personalizada — sem criar conta. Windows Server
              2016 ou 2019. 30 GB de disco na VPS · 20 GB no CyberCloud incluídos · VPS 300 Mb/s
              · Semi 500 Mb/s. Cada plano soma espaço extra na nuvem.
            </p>
          </div>
          <VpsPriceSimulator />
        </div>
      </section>

      <section id="recursos" className="py-20 sm:py-24">
        <div className="max-w-cyber mx-auto px-4 sm:px-6">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">Por que escolher a CyberHost?</h2>
            <p className="text-[var(--text-secondary)] max-w-2xl mx-auto">
              Infraestrutura de classe mundial para suas aplicações mais exigentes
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {features.map((f) => {
              const FeatureSvg = f.svg;
              return (
                <div key={f.title} className="feature-card-marketing">
                  <div className="feature-icon-box">
                    <FeatureSvg className="w-7 h-7" />
                  </div>
                  <h3 className="text-xl font-bold mb-3">{f.title}</h3>
                  <p className="text-[var(--text-secondary)] text-sm leading-relaxed mb-4">{f.desc}</p>
                  <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--accent)]">
                    Saiba mais
                    <SvgArrowRight />
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section id="tecnologias" className="py-20 sm:py-24 bg-[var(--bg-elevated)]">
        <div className="max-w-cyber mx-auto px-4 sm:px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">Compatível com suas tecnologias favoritas</h2>
            <p className="text-[var(--text-secondary)] max-w-2xl mx-auto">
              FiveM, Minecraft, MTA, Rust, DayZ e outros rodam na VPS Windows com RDP e controle total.
            </p>
          </div>

          <div className="flex flex-wrap justify-center gap-8 sm:gap-12 mb-10">
            {technologies.map((t) => (
              <div key={t.name} className="flex flex-col items-center gap-3 group">
                <div className="w-20 h-20 rounded-2xl bg-[var(--glass-bg)] border border-[var(--glass-border)] p-3 flex items-center justify-center group-hover:border-[var(--accent)] transition-colors shadow-md">
                  <Image src={publicAsset(t.src)} alt={t.name} width={56} height={56} className="object-contain" />
                </div>
                <span className="text-sm font-medium text-[var(--text-secondary)]">{t.name}</span>
              </div>
            ))}
          </div>

          <div className="flex flex-col sm:flex-row justify-center items-center gap-4">
            {WEB_HOSTING_ENABLED && (
              <Link href="/order/web" className="btn-primary !px-6 !py-2.5 text-sm">
                Contratar hospedagem de site
              </Link>
            )}
            {GAME_HOSTING_ENABLED && (
              <Link href="/order/game" className="btn-primary !px-6 !py-2.5 text-sm">
                Contratar servidor de jogo
              </Link>
            )}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[var(--glass-bg)] border border-[var(--glass-border)] text-sm">
              <Image src={publicAsset("/br.png")} alt="Brasil" width={24} height={16} className="rounded-sm" />
              Servidores localizados no Brasil
            </div>
          </div>
        </div>
      </section>

      <section className="py-20 sm:py-24">
        <div className="max-w-cyber mx-auto px-4 sm:px-6">
          <div className="glass-card p-10 sm:p-14 text-center border-[var(--accent)]/20">
            <div className="inline-flex items-center gap-2 mb-6">
              <Image src={publicAsset("/br.png")} alt="Brasil" width={28} height={18} className="rounded-sm" />
              <span className="text-sm font-medium text-[var(--accent)]">Painel de provisionamento automático</span>
            </div>
            <h2 className="text-3xl font-bold mb-4">Configure sua VPS em minutos</h2>
            <p className="text-[var(--text-secondary)] max-w-xl mx-auto mb-8">
              Escolha vCPU e RAM, pague via PIX e acompanhe a criação do servidor em tempo real no painel.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Link href="/register" className="btn-primary !px-8 !py-3.5">
                Criar conta grátis
              </Link>
              <Link href="/order" className="btn-ghost-marketing !px-8 !py-3.5">
                Configurar VPS
              </Link>
            </div>
          </div>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
