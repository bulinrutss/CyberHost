const GAME_PROVISION_STEP_LABELS: Record<string, string> = {
  payment_pending: "Aguardando pagamento",
  payment_confirmed: "Pagamento confirmado",
  allocating_port: "Alocando porta",
  deploying_files: "Preparando arquivos",
  configuring: "Configurando servidor",
  ready: "Servidor pronto",
  failed: "Falha no provisionamento",
};

export function gameProvisionStepLabel(step: string | null | undefined): string | null {
  if (!step) return null;
  return GAME_PROVISION_STEP_LABELS[step] ?? step.replace(/_/g, " ");
}

export function formatBRL(cents: number): string {
  return (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
