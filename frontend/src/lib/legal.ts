export const LEGAL_CONTACT_EMAIL = "cyberhost@ruts.dev";
export const LEGAL_CNPJ = "52.983.358/0001-85";
export const LEGAL_UPDATED_AT = "25 de agosto de 2026";

export type LegalSection = {
  title: string;
  paragraphs: string[];
};

export const TERMS_OF_USE: LegalSection[] = [
  {
    title: "1. Quem somos",
    paragraphs: [
      `Estes Termos de Uso regulam o acesso e a contratação dos serviços de hospedagem da CyberHost, inscrita no CNPJ ${LEGAL_CNPJ}, disponíveis em ruts.dev/cyberhost.`,
      `O contato oficial é o e-mail ${LEGAL_CONTACT_EMAIL}. Ao criar uma conta, pagar um pedido ou usar o painel, você concorda com estes Termos e com a Política de Privacidade.`,
    ],
  },
  {
    title: "2. Serviços oferecidos",
    paragraphs: [
      "A CyberHost oferece (i) servidores virtuais Windows (VPS) com acesso remoto; (ii) hospedagem de servidores de jogo (Game Hosting) com painel de arquivos e controles de iniciar, parar e reiniciar; e (iii) armazenamento em nuvem (CyberCloud), com cota base na conta e eventuais pacotes adicionais.",
      "Os recursos (vCPU, memória, disco, banda, portas, cota de arquivos e limites do plano) são os descritos no momento da contratação. Valores, prazos e especificações do checkout prevalecem sobre textos promocionais da página inicial.",
    ],
  },
  {
    title: "3. Conta e elegibilidade",
    paragraphs: [
      "Você deve informar dados verdadeiros, manter o telefone e a senha em sigilo e ser civilmente capaz. Contas são pessoais: o titular responde por todas as ações feitas com suas credenciais, inclusive por usuários a quem conceder acesso.",
      "Podemos recusar, suspender ou encerrar contas em caso de dados falsos, inadimplência, abuso técnico, conteúdo ilícito ou violação destes Termos.",
    ],
  },
  {
    title: "4. Pagamento, renovação e cancelamento",
    paragraphs: [
      "Os serviços são pré-pagos, em reais, via Pix. O provisionamento ou o crédito de cota ocorre após a confirmação do pagamento pelo provedor. Pedidos pendentes podem ser cancelados se o Pix não for pago no prazo.",
      "A renovação não é automática por cartão: o titular deve renovar no painel enquanto o serviço estiver ativo. O não pagamento até o vencimento pode gerar suspensão, bloqueio de acesso e, após o prazo interno de carência, exclusão definitiva de VPS, arquivos de jogo e dados do CyberCloud, sem obrigação de backup nosso.",
      "Valores já pagos por período iniciado, em regra, não são reembolsados, ressalvados o direito de arrependimento de 7 dias previsto no CDC para o consumidor, quando aplicável, e falha imputável à CyberHost que impeça o uso substancial do serviço contratado.",
    ],
  },
  {
    title: "5. Uso aceitável",
    paragraphs: [
      "É vedado usar os serviços para atividade ilícita, fraude, phishing, spam, ataque a terceiros, mineração abusiva, distribuição de malware, material de exploração sexual de menores, violação de direitos autorais ou qualquer conteúdo cuja hospedagem seja proibida no Brasil.",
      "Você não deve tentar escapar de isolamento, explorar falhas, sobrecarregar a rede compartilhada, escanear portas de terceiros a partir da nossa infraestrutura ou revender o serviço sem autorização escrita.",
      "Servidores de jogo e VPS devem respeitar os limites de CPU, memória, disco, processos e banda do plano. Excesso persistente pode ser limitado ou suspenso para proteger os demais clientes.",
    ],
  },
  {
    title: "6. Conteúdo, backups e responsabilidade do cliente",
    paragraphs: [
      "O conteúdo armazenado na VPS, no Game Hosting e no CyberCloud é de sua responsabilidade. A CyberHost não revisa arquivos de forma contínua e não substitui a sua política de backup.",
      "Embora adotemos medidas técnicas razoáveis, falhas de hardware, rede, software ou de terceiros podem ocorrer. Mantenha cópias próprias do que for crítico. A exclusão de conta, o vencimento sem renovação ou a violação destes Termos podem apagar dados de forma irreversível.",
    ],
  },
  {
    title: "7. Disponibilidade e suporte",
    paragraphs: [
      "Trabalhamos para manter os serviços no ar com a melhor disponibilidade possível. Manutenções programadas, falhas de operadora, de energia ou de provedores de pagamento e armazenamento podem causar interrupções. Não há crédito automático por indisponibilidade, salvo se anunciado por escrito para o seu contrato.",
      `O suporte é prestado pelo e-mail ${LEGAL_CONTACT_EMAIL} e pelos canais oficiais indicados no site. Prazos de resposta variam conforme a fila e a gravidade.`,
    ],
  },
  {
    title: "8. Propriedade intelectual",
    paragraphs: [
      "Marcas, layout, painel, textos e software da CyberHost permanecem de nossa titularidade ou de licenciadores. É concedida apenas a licença de uso do serviço contratado, não exclusiva e intransferível. Softwares de terceiro (sistemas operacionais, jogos, painéis) seguem as licenças dos respectivos titulares — cabe a você obtê-las quando exigidas.",
    ],
  },
  {
    title: "9. Limitação de responsabilidade",
    paragraphs: [
      "Na máxima medida permitida pela lei, a CyberHost não responde por lucros cessantes, perda de dados do cliente, danos indiretos ou uso indevido da conta. Em qualquer hipótese, a responsabilidade total fica limitada ao valor efetivamente pago pelo serviço afetado nos 30 dias anteriores ao evento, sem prejuízo dos direitos irrenunciáveis do consumidor.",
    ],
  },
  {
    title: "10. Alterações e foro",
    paragraphs: [
      "Estes Termos podem ser atualizados. A versão vigente será a publicada no site, com a data de atualização. O uso continuado após a publicação implica concordância, quando a lei permitir.",
      "Aplica-se a legislação brasileira. Fica eleito o foro do domicílio do consumidor, quando aplicável o CDC; nos demais casos, o foro da comarca de Florianópolis/SC.",
    ],
  },
];

export const PRIVACY_POLICY: LegalSection[] = [
  {
    title: "1. Controladora e contato",
    paragraphs: [
      `A CyberHost, CNPJ ${LEGAL_CNPJ}, é a controladora dos dados pessoais tratados para prestar hospedagem VPS, Game Hosting e CyberCloud.`,
      `Para exercer direitos ou tirar dúvidas sobre privacidade, escreva para ${LEGAL_CONTACT_EMAIL} com o assunto “Privacidade / LGPD”.`,
    ],
  },
  {
    title: "2. Quais dados coletamos",
    paragraphs: [
      "Cadastro: nome, telefone e senha (esta última armazenada de forma irreversível). Administradores podem cadastrar autenticação em dois fatores.",
      "Contratação e pagamento: dados do pedido (plano, recursos, valores, identificadores de cobrança Pix) e o status informado pelo provedor de pagamento. Não armazenamos o QR Code além do necessário para o checkout.",
      "Uso do serviço: endereços IP de acesso ao painel, registros de autenticação, tickets de console, logs técnicos, métricas da VPS e metadados de arquivos (nome, tamanho, data) no CyberCloud e no Game Hosting.",
      "Conteúdo que você envia: arquivos da nuvem, configurações e arquivos do servidor de jogo, e dados existentes dentro da VPS. Esse conteúdo é tratado para hospedá-lo, não para fins de marketing.",
    ],
  },
  {
    title: "3. Para que usamos os dados",
    paragraphs: [
      "Prestar o serviço contratado (criar conta, provisionar VPS, hospedar jogos, armazenar arquivos, renovar e cobrar).",
      "Autenticar o acesso, prevenir fraude e abuso, aplicar limites de uso e cumprir obrigações legais (notas, defesa em processo, ordens de autoridade).",
      "Comunicar avisos operacionais, vencimento, suporte e alterações relevantes dos termos. Não vendemos sua lista de contatos.",
    ],
  },
  {
    title: "4. Bases legais (LGPD)",
    paragraphs: [
      "Execução de contrato (art. 7º, V) para cadastro, cobrança e operação da hospedagem.",
      "Cumprimento de obrigação legal ou regulatória (art. 7º, II) quando exigido, por exemplo em registros fiscais ou atendimento a autoridade.",
      "Legítimo interesse (art. 7º, IX) para segurança da infraestrutura, logs de acesso e prevenção a abuso, sempre de forma proporcional.",
      "Consentimento, quando um recurso opcional o exigir — você pode revogá-lo pelo e-mail de privacidade, sem prejuízo do serviço essencial já contratado.",
    ],
  },
  {
    title: "5. Com quem compartilhamos",
    paragraphs: [
      "Provedor de pagamento Pix, para gerar cobrança, confirmar pagamento e reconciliar o pedido.",
      "Infraestrutura de virtualização e rede necessária para rodar a VPS e expor portas contratadas.",
      "Operadores de armazenamento e entrega de arquivos do CyberCloud, estritamente para guardar e recuperar os fragmentos que você enviou.",
      "Autoridades públicas, quando houver obrigação legal, ordem judicial ou requisição válida. Não comercializamos dados pessoais.",
    ],
  },
  {
    title: "6. Retenção e segurança",
    paragraphs: [
      "Mantemos os dados enquanto a conta e os serviços estiverem ativos e pelo prazo adicional necessário a cobrança, auditoria, defesa legal e obrigações fiscais.",
      "Após exclusão ou encerramento, arquivos e máquinas podem ser apagados de forma permanente. Logs técnicos podem permanecer por período limitado para segurança.",
      "Adotamos medidas como sessão em cookie HttpOnly, cifração de senhas administrativas de Windows no banco, isolamento de processos de jogo e restrição de acesso interno. Nenhum sistema é 100% isento de risco; notifique-nos se identificar incidente.",
    ],
  },
  {
    title: "7. Seus direitos",
    paragraphs: [
      "Você pode solicitar confirmação de tratamento, acesso, correção, anonimização, portabilidade (quando aplicável), eliminação de dados desnecessários, informação sobre compartilhamentos e revogação de consentimento.",
      `Pedidos devem ser feitos por ${LEGAL_CONTACT_EMAIL}, com identificação razoável do titular. Poderemos recusar pedidos que inviabilizem o contrato em vigor, a segurança de terceiros ou o cumprimento da lei.`,
      "Se não ficar satisfeito com nossa resposta, você pode contatar a Autoridade Nacional de Proteção de Dados (ANPD).",
    ],
  },
  {
    title: "8. Cookies e painel",
    paragraphs: [
      "O painel usa cookie de sessão essencial (não de publicidade) para manter você autenticado. Preferência de tema pode ser guardada no navegador. Não utilizamos redes de anúncio de terceiros na área logada.",
    ],
  },
  {
    title: "9. Alterações",
    paragraphs: [
      `Esta política pode mudar para refletir novos serviços ou exigências legais. A data da última atualização é ${LEGAL_UPDATED_AT}. A versão vigente é a exibida neste site.`,
    ],
  },
];
