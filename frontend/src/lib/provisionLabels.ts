const PROVISION_STEP_LABELS: Record<string, string> = {
  payment_pending: "Aguardando pagamento",
  payment_confirmed: "Pagamento confirmado",
  preparing: "Preparando servidor",
  copying_disk: "Copiando disco do template",
  registering: "Registrando servidor",
  configuring: "Configurando CPU e RAM",
  powering_off: "Desligando servidor",
  powering_on: "Ligando servidor",
  starting_os: "Inicializando Windows",
  waiting_tools: "Aguardando o Windows iniciar",
  waiting_auth: "Autenticando no Windows",
  configuring_network: "Configurando rede",
  extending_disk: "Expandindo disco",
  rearming_windows: "Resetando prazo de ativação Windows",
  rebooting: "Reiniciando para aplicar rearm",
  applying_upgrade: "Aplicando upgrade",
  admin_applied: "Alteração aplicada",
  ready: "Servidor pronto",
  failed: "Falha no provisionamento",
};

export function provisionStepLabel(step: string | null | undefined): string | null {
  if (!step) return null;
  return PROVISION_STEP_LABELS[step] ?? step.replace(/_/g, " ");
}
