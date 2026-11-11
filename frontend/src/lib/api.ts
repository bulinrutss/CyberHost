import { API_URL } from "@/lib/apiBase";
import { clearStepUpToken, ensureStepUp, peekStepUpToken } from "@/lib/stepUp";
import { clearFinanceToken } from "@/lib/financeSession";

function isCloudPath(path: string): boolean {
  return path.includes("/api/files");
}

function cloudApiLog(direction: string, method: string, path: string, extra?: unknown): void {
  const full = `${API_URL}${path}`;
  const prefix = `[CloudFiles API] ${direction} ${method} ${full}`;
  if (extra !== undefined) console.log(prefix, extra);
  else console.log(prefix);
}

export type User = {
  id: number;
  phone: string;
  email?: string | null;
  name: string;
  is_active: boolean;
  is_admin: boolean;
  mfa_enabled?: boolean;
  created_at: string;
};

export type PhoneVerificationStatus = {
  required: boolean;
  channel: string | null;
};

export type WhatsAppSendResult = {
  ticket: string;
  expires_in: number;
  retry_after: number;
};

export type LoginResult = {
  access_token?: string;
  authenticated?: boolean;
  token_type?: string;
  mfa_required?: boolean;
  mfa_setup_required?: boolean;
  mfa_ticket?: string | null;
  mfa_secret?: string | null;
  otpauth_url?: string | null;
};

export type AuthSessionItem = {
  id: number;
  device_id: string;
  user_agent: string;
  ip: string;
  created_at: string;
  last_seen_at: string;
  current: boolean;
};

export type PasskeyItem = {
  id: number;
  device_name: string;
  created_at: string;
  last_used_at: string | null;
};

export type MfaSetupStart = {
  mfa_ticket: string;
  mfa_secret: string;
  otpauth_url: string;
};

export type VpsBilling = {
  billing_state: "active" | "grace" | "suspended";
  billing_label: string;
  paid_until: string;
  grace_ends_at: string;
  billing_day: number;
  monthly_cents: number | null;
  suspended_for_billing: boolean;
  days_until_due: number;
  days_in_grace_left: number;
  can_power_on: boolean;
};

export type VpsInstance = {
  id: number;
  vm_name: string;
  vcpu: number;
  ram_mb: number;
  disk_gb: number;
  os_template?: string | null;
  os_label?: string | null;
  network_mbps: number;
  plan_slug: string | null;
  plan_name: string | null;
  ip_address: string | null;
  status: string;
  esxi_host: string;
  error_message: string | null;
  is_provisioning: boolean;
  provision_progress: number | null;
  provision_label: string | null;
  billing: VpsBilling | null;
  created_at: string;
};

export type VpsMetrics = {
  cpu_allocated: number;
  ram_allocated_mb: number;
  disk_allocated_gb: number | null;
  cpu_usage_percent: number | null;
  ram_used_mb: number | null;
  ram_usage_percent: number | null;
  disk_used_gb: number | null;
  disk_free_gb: number | null;
  disk_usage_percent: number | null;
  disk_source: string;
  uptime_seconds: number | null;
  guest_os: string | null;
  guest_ip: string | null;
};

export type VpsInstanceList = VpsInstance & {
  power_state: string;
  cpu_usage_percent: number | null;
  ram_usage_percent: number | null;
  disk_allocated_gb: number | null;
  disk_usage_percent: number | null;
};

export type OsTemplateOption = {
  slug: string;
  label: string;
  template_name: string;
  is_recommended: boolean;
  recommended_min_vcpu: number;
  recommended_min_ram_mb: number;
  recommended_min_disk_gb: number;
  description: string;
};

export type WindowsCredentials = {
  username: string;
  password?: string | null;
  has_password?: boolean;
};

export type StepUpResult = {
  step_up_token: string;
  expires_in: number;
  mfa_enabled: boolean;
};

export type VpsPortMapping = {
  public_host: string;
  public_port: number;
  internal_host: string;
  internal_port: number;
  connection_address: string;
  label: string;
};

export type VpsConnectionDomain = {
  id: number;
  domain: string;
  public_port: number;
  internal_port: number;
  http_proxy: boolean;
  ssl_active: boolean;
  created_at: string;
};

export type VpsInstanceDetail = VpsInstance & {
  power_state: string;
  tools_ok: boolean;
  metrics: VpsMetrics;
  os_template?: string | null;
  os_label?: string | null;
  windows_credentials?: WindowsCredentials | null;
  port_mappings?: VpsPortMapping[];
  connection_domains?: VpsConnectionDomain[];
  dns_target?: string;
  rdp_connection_address?: string | null;
};

export type VpsConsoleInfo = {
  available: boolean;
  power_state: string;
  ws_path: string;
  message: string | null;
};

export type VpsConsoleTicket = {
  wss_url: string;
  host: string;
  port: number;
  expires_in_seconds: number;
};

export type VpsConsoleWsTicket = {
  ticket: string;
  expires_in_seconds: number;
  ws_path: string;
};

export type HostFileEntry = {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  modified_at: string | null;
};

export type HostFileList = {
  path: string;
  parent: string | null;
  entries: HostFileEntry[];
};

export type HostFileContent = {
  path: string;
  content: string;
  size: number;
};

export type HostShellTicket = {
  ticket: string;
  expires_in_seconds: number;
  ws_path: string;
  available: boolean;
  message: string | null;
};

export type HostMetrics = {
  collected_at: string;
  hostname: string;
  pretty_name: string | null;
  kernel: string;
  architecture: string;
  uptime_seconds: number;
  process_count: number;
  cpu: {
    percent: number | null;
    cores: number;
    load_1: number | null;
    load_5: number | null;
    load_15: number | null;
    per_cpu: number[];
  };
  memory: {
    total_bytes: number;
    used_bytes: number;
    available_bytes: number;
    percent: number;
    swap_total_bytes: number;
    swap_used_bytes: number;
    swap_percent: number;
  };
  disks: Array<{
    mount: string;
    fstype: string;
    total_bytes: number;
    used_bytes: number;
    free_bytes: number;
    percent: number;
  }>;
  disk_io: {
    read_bytes_per_sec: number | null;
    write_bytes_per_sec: number | null;
  };
  network: Array<{
    name: string;
    rx_bytes: number;
    tx_bytes: number;
    rx_bytes_per_sec: number | null;
    tx_bytes_per_sec: number | null;
    rx_errors: number;
    tx_errors: number;
    rx_dropped: number;
    tx_dropped: number;
  }>;
  top_memory: Array<{
    pid: number;
    name: string;
    rss_bytes: number;
  }>;
  temperature_c: number | null;
};

export function buildConsoleWsUrl(instanceId: number, ticket: string): string | null {
  if (!ticket) return null;
  const base =
    API_URL ||
    (typeof window !== "undefined" ? window.location.origin : "http://localhost:8810");
  const wsBase = base.replace(/^http:\/\//i, "ws://").replace(/^https:\/\//i, "wss://");
  return `${wsBase}/api/vps/instances/${instanceId}/console/ws?ticket=${encodeURIComponent(ticket)}`;
}

export function buildHostShellWsUrl(ticket: string): string | null {
  if (!ticket) return null;
  const base =
    API_URL ||
    (typeof window !== "undefined" ? window.location.origin : "http://localhost:8810");
  const wsBase = base.replace(/^http:\/\//i, "ws://").replace(/^https:\/\//i, "wss://");
  return `${wsBase}/api/admin/host/shell/ws?ticket=${encodeURIComponent(ticket)}`;
}

export type VpsInstanceAdmin = VpsInstance & {
  user_id: number;
  user_phone: string;
  user_name: string;
};

export type VpsInstanceAdminDetail = VpsInstanceAdmin & {
  power_state: string;
  tools_ok: boolean;
  metrics: VpsMetrics;
  custom_monthly_cents: number | null;
  os_template?: string | null;
  os_label?: string | null;
  windows_credentials?: WindowsCredentials | null;
  rdp_connection_address?: string | null;
};

export type WebSiteAdmin = WebSite & {
  user_id: number;
  user_phone: string;
  user_name: string;
};

export type WebSiteAdminDetail = WebSiteAdmin;

export type NginxProxyMode = "reverse_proxy" | "redirect";
export type NginxProxyKind = "manual" | "web_site" | "vps_connection";

export type NginxProxyEntry = {
  key: string;
  kind: NginxProxyKind;
  reference_id: number | null;
  domain: string;
  mode: NginxProxyMode;
  target: string;
  include_www: boolean;
  ssl_active: boolean;
  editable: boolean;
  deletable: boolean;
  label: string;
  notes: string | null;
  created_at: string | null;
};

export type DiscountCoupon = {
  id: number;
  code: string;
  description: string;
  discount_percent: number | null;
  discount_cents: number | null;
  max_uses: number | null;
  used_count: number;
  valid_from: string | null;
  valid_until: string | null;
  is_active: boolean;
  created_at: string;
};

export type CloudFileItem = {
  id: number;
  parent_id: number | null;
  name: string;
  is_folder: boolean;
  size_bytes: number;
  mime_type: string | null;
  chunk_count: number;
  storage_backend: string;
  upload_status: string;
  created_at: string;
  updated_at: string;
};

export type CloudBilling = {
  billing_state: "none" | "active" | "grace" | "suspended";
  billing_label: string;
  paid_until: string | null;
  grace_ends_at: string | null;
  billing_day: number;
  monthly_cents: number;
  contracted_gb: number;
  suspended_for_billing: boolean;
  days_until_due: number;
  days_in_grace_left: number;
  can_upload: boolean;
};

export type CloudQuota = {
  used_bytes: number;
  quota_bytes: number;
  base_bytes: number;
  vps_bonus_bytes: number;
  subscribed_bytes: number;
  bonus_bytes: number;
  extra_bytes: number;
  contracted_gb: number;
  billing: CloudBilling | null;
  chunk_size_bytes: number;
  max_upload_bytes: number;
};

export type GameTypeInfo = {
  slug: string;
  label: string;
  description: string;
  default_port: number;
};

export type GamePreset = {
  id: number;
  game_type: string;
  slug: string;
  name: string;
  slots: number;
  ram_mb: number;
  price_cents: number;
  is_popular: boolean;
  sort_order: number;
};

export type GameServer = {
  id: number;
  game_type: string;
  game_label: string;
  server_name: string;
  slots: number;
  ram_mb: number;
  port: number;
  query_port: number | null;
  public_ip: string;
  address: string;
  status: string;
  is_provisioning: boolean;
  config_file: string;
  error_message: string | null;
  billing: {
    paid_until: string;
    billing_day: number;
    monthly_cents: number;
    suspended_for_billing: boolean;
  } | null;
  created_at: string;
};

export type GameOrder = {
  id: number;
  game_type: string;
  preset_id: number | null;
  slots: number;
  ram_mb: number;
  server_name: string;
  total_cents: number;
  status: string;
  payment_checkout_url: string | null;
  pix_br_code?: string | null;
  pix_qr_base64?: string | null;
  pix_expires_at?: string | null;
  provision_progress: number;
  provision_step: string | null;
  provision_label: string | null;
  error_message: string | null;
  created_at: string;
};

export type WebPreset = {
  id: number;
  slug: string;
  name: string;
  ram_mb: number;
  disk_mb: number;
  cpu_percent: number;
  php_enabled: boolean;
  price_cents: number;
  cloud_bonus_gb?: number;
  is_popular: boolean;
  sort_order: number;
};

export type WebSite = {
  id: number;
  site_slug: string;
  domain: string | null;
  path_url: string;
  ram_mb: number;
  disk_mb: number;
  cpu_percent: number;
  php_enabled: boolean;
  port: number;
  status: string;
  is_provisioning: boolean;
  error_message: string | null;
  public_url: string;
  dns_target: string;
  ssl_active?: boolean;
  billing: {
    billing_state: "active" | "grace" | "suspended" | "none";
    billing_label: string;
    paid_until: string;
    grace_ends_at?: string | null;
    billing_day: number;
    monthly_cents: number;
    suspended_for_billing: boolean;
    days_until_due: number;
    days_in_grace_left: number;
    can_power_on: boolean;
  } | null;
  created_at: string;
  data_used_bytes?: number;
  provision_progress?: number | null;
  provision_label?: string | null;
};

export type WebPageLink = {
  id: string;
  label: string;
  url: string;
  icon?: string | null;
};

export type WebPageLinkIconOption = {
  id: string;
  label: string;
};

export type WebPageTemplate = {
  id: string;
  name: string;
  description: string;
  preview_accent: string;
  preview_background: string;
};

export type WebPageConfig = {
  template_id: string;
  title: string;
  subtitle: string;
  avatar_path?: string | null;
  accent_color: string;
  background_color: string;
  text_color: string;
  links: WebPageLink[];
};

export type WebPageEditor = {
  templates: WebPageTemplate[];
  link_icons?: WebPageLinkIconOption[];
  config: WebPageConfig | null;
  using_builder: boolean;
  avatar_url?: string | null;
};

export type WebSiteAnalyticsDay = {
  date: string;
  page_views: number;
  link_clicks: number;
  unique_visitors: number;
};

export type WebSiteLinkClickStat = {
  link_id: string;
  label: string;
  clicks: number;
};

export type WebSiteAnalytics = {
  days: number;
  generated_at: string;
  page_views: number;
  link_clicks: number;
  unique_visitors: number;
  click_rate_pct: number;
  daily: WebSiteAnalyticsDay[];
  links: WebSiteLinkClickStat[];
};

export type WebOrder = {
  id: number;
  order_type?: string;
  target_site_id?: number | null;
  renewal_months?: number | null;
  preset_id: number | null;
  site_slug: string;
  domain: string | null;
  ram_mb: number;
  disk_mb: number;
  cpu_percent: number;
  php_enabled: boolean;
  subtotal_cents?: number | null;
  discount_cents?: number;
  total_cents: number;
  status: string;
  payment_checkout_url: string | null;
  pix_br_code?: string | null;
  pix_qr_base64?: string | null;
  pix_expires_at?: string | null;
  provision_progress: number;
  provision_step: string | null;
  provision_label: string | null;
  error_message: string | null;
  created_at: string;
};

export type VpsOrder = {
  id: number;
  status: string;
  hostname: string;
  order_type: string;
  target_instance_id: number | null;
  vcpu: number;
  ram_mb: number;
  disk_gb: number;
  renewal_months: number | null;
  total_cents: number;
  payment_checkout_url: string | null;
  pix_br_code?: string | null;
  pix_qr_base64?: string | null;
  pix_expires_at?: string | null;
  provision_progress: number;
  provision_label: string | null;
  error_message: string | null;
  notes?: string | null;
  created_at: string;
};

export type CloudStorageOrder = {
  id: number;
  extra_gb: number;
  renewal_months: number | null;
  total_cents: number;
  status: string;
  pix_br_code?: string | null;
  pix_qr_base64?: string | null;
  pix_expires_at?: string | null;
  notes?: string | null;
  created_at: string;
};

export type GameFileEntry = {
  name: string;
  path: string;
  is_dir: boolean;
  size_bytes: number;
};

export type CloudStoragePackage = {
  slug: string;
  gb: number;
  price_cents: number;
};

export type CloudStorageQuote = CloudStoragePackage & {
  list_price_cents: number;
  total_cents: number;
  monthly_price_cents: number;
  paid_until: string | null;
  monthly_delta_cents: number;
  amount_cents: number;
  days_remaining: number;
  period_days: number;
  prorated: boolean;
};

export type AdminCloudQuotaInfo = {
  used_bytes: number;
  quota_bytes: number;
  base_bytes: number;
  vps_bonus_bytes: number;
  subscribed_bytes: number;
  bonus_bytes: number;
  extra_bytes: number;
  contracted_gb: number;
  cloud_paid_until: string | null;
  cloud_billing_day: number;
  cloud_monthly_cents: number;
  cloud_suspended_for_billing: boolean;
  admin_pending_cloud_charge_cents: number;
  billing: CloudBilling | null;
};

export type PixDevItem = {
  charge_id: string;
  ok: boolean;
  action: "released" | "already" | "failed" | string;
  detail: string;
  kind: string | null;
  order_id: number | null;
  order_status: string | null;
  simulated: boolean;
};

export type PixDevResponse = {
  results: PixDevItem[];
  released: number;
  skipped: number;
  failed: number;
};

export type AdminVpsSummary = {
  id: number;
  vm_name: string;
  vcpu: number;
  ram_mb: number;
  disk_gb: number;
  status: string;
  ip_address: string | null;
  paid_until: string | null;
  monthly_cents: number | null;
  custom_monthly_cents: number | null;
  admin_pending_charge_cents: number;
  suspended_for_billing: boolean;
};

export type AdminWebSiteSummary = {
  id: number;
  site_slug: string;
  domain?: string | null;
  ram_mb: number;
  disk_mb: number;
  php_enabled: boolean;
  port: number;
  status: string;
  paid_until?: string | null;
  suspended_for_billing?: boolean;
};

export type AdminOrderSummary = {
  kind: "vps" | "game" | "cloud" | string;
  id: number;
  title: string;
  description: string;
  status: string;
  total_cents: number;
  created_at: string;
  error_message: string | null;
  can_delete?: boolean;
};

export type AdminUserDetail = {
  id: number;
  phone: string;
  email?: string | null;
  name: string;
  is_active: boolean;
  is_admin: boolean;
  mfa_enabled?: boolean;
  created_at: string;
  cloud: AdminCloudQuotaInfo;
  vps_instances: AdminVpsSummary[];
  web_sites?: AdminWebSiteSummary[];
  orders?: AdminOrderSummary[];
};

export type AdminAccountDeletionPreview = {
  id: number;
  name: string;
  phone: string;
  email?: string | null;
  is_admin: boolean;
  created_at: string;
  vps: Array<{
    id: number;
    vm_name: string;
    status: string;
    ip_address: string | null;
    vcpu: number;
    ram_mb: number;
    disk_gb: number;
  }>;
  game_servers: Array<{
    id: number;
    server_name: string;
    game_type: string;
    status: string;
    port: number;
  }>;
  web_sites?: Array<{
    id: number;
    site_slug: string;
    domain?: string | null;
    status: string;
    port: number;
  }>;
  cloud: { files: number; folders: number; used_bytes: number };
  orders: { vps: number; cloud: number; game: number; web?: number; pending_payment: number };
  warnings: string[];
};

export type AdminAccountDeleteResult = {
  deleted_user_id: number;
  destroyed_vms: string[];
  stopped_game_servers: number;
  deleted_web_sites?: number;
  deleted_cloud_files: number;
};

export type AdminStats = {
  days: number;
  generated_at: string;
  clients: { total: number; active: number; admins: number };
  orders: {
    total: number;
    completed: number;
    pending: number;
    denied: number;
    error: number;
    other: number;
    revenue_cents: number;
    by_kind: Record<string, number>;
    by_status: Record<string, number>;
  };
  host: {
    vps_total: number;
    vps_running: number;
    vps_stopped: number;
    vps_error: number;
    vps_suspended: number;
    vps_by_status: Record<string, number>;
    allocated_vcpu: number;
    allocated_ram_mb: number;
    allocated_disk_gb: number;
    game_servers: number;
    cloud_used_bytes: number;
    cloud_files: number;
    cloud_contracted_gb: number;
    cloud_suspended_users: number;
  };
  daily: Array<{
    date: string;
    completed: number;
    pending: number;
    denied: number;
    error: number;
    other: number;
    revenue_cents: number;
    total: number;
  }>;
  top_clients: Array<{
    id: number;
    name: string;
    phone: string;
    is_active: boolean;
    vps_count: number;
    vps_running: number;
    vps_error: number;
    orders: number;
    spent_cents: number;
    order_errors: number;
    cloud_gb: number;
    cloud_suspended: boolean;
  }>;
  machines: Array<{
    id: number;
    vm_name: string;
    status: string;
    vcpu: number;
    ram_mb: number;
    disk_gb: number;
    ip_address: string | null;
    paid_until: string | null;
    suspended_for_billing: boolean;
    error_message: string | null;
    user_id: number;
    user_name: string;
    user_phone: string;
  }>;
  events: Array<{
    at: string | null;
    level: string;
    source: string;
    title: string;
    subject: string | null;
    status: string;
    detail: string | null;
    user_id: number | null;
    user_name: string;
    user_phone: string;
    total_cents: number;
    instance_id?: number | null;
    order_id?: number | null;
    can_delete?: boolean;
  }>;
};

export type AdminAnalytics = {
  days: number;
  generated_at: string;
  totals: {
    page_views: number;
    clicks: number;
    forms: number;
    page_leaves: number;
    unique_visitors: number;
    unique_sessions: number;
    identified_users: number;
    avg_duration_ms: number;
    avg_scroll_pct: number;
  };
  auth: { anonymous: number; logged_in: number; admin: number };
  daily: Array<{ date: string; page_views: number; clicks: number; forms: number; visitors: number }>;
  hourly: Array<{ hour: string; page_views: number; clicks: number }>;
  top_pages: Array<{ key: string; count: number; unique: number }>;
  top_clicks: Array<{ key: string; count: number; unique: number }>;
  top_forms: Array<{ key: string; count: number; unique: number }>;
  top_entry: Array<{ key: string; count: number; unique: number }>;
  browsers: Array<{ key: string; count: number; unique: number }>;
  systems: Array<{ key: string; count: number; unique: number }>;
  languages: Array<{ key: string; count: number; unique: number }>;
  referrers: Array<{ key: string; count: number; unique: number }>;
  viewports: Array<{ key: string; count: number; unique: number }>;
  recent: Array<{
    at: string;
    name: string;
    path: string;
    label: string;
    user_name: string | null;
    is_admin: boolean;
  }>;
};

export type AdminCloudAdjustResult = {
  extra_gb_added: number;
  charge_mode: string;
  charged_cents: number;
  deferred_cents: number;
  checkout_url: string | null;
  pix_br_code?: string | null;
  pix_qr_base64?: string | null;
  pix_expires_at?: string | null;
  order_id: number | null;
  cloud: AdminCloudQuotaInfo;
};

export type AdminVpsUpdateResult = {
  instance_id: number;
  charge_mode: string;
  charged_cents: number;
  deferred_cents: number;
  checkout_url: string | null;
  pix_br_code?: string | null;
  pix_qr_base64?: string | null;
  pix_expires_at?: string | null;
  order_id: number | null;
  proration: {
    monthly_delta_cents: number;
    amount_cents: number;
    days_remaining: number;
    period_days: number;
    prorated: boolean;
  } | null;
  vcpu: number;
  ram_mb: number;
  disk_gb: number;
};

export type CloudStoragePurchaseResult = {
  order_id: number;
  checkout_url: string | null;
  pix_br_code?: string | null;
  pix_qr_base64?: string | null;
  pix_expires_at?: string | null;
  extra_gb: number;
  total_cents: number;
  status: string;
};

export type CloudStorageRenewQuote = {
  months: number;
  monthly_cents: number;
  total_cents: number;
  pending_cents: number;
  new_paid_until: string;
  contracted_gb: number;
  billing: CloudBilling;
};

export type CloudStorageRenewResult = {
  order_id: number;
  checkout_url: string | null;
  pix_br_code?: string | null;
  pix_qr_base64?: string | null;
  pix_expires_at?: string | null;
  renewal_months: number;
  total_cents: number;
  status: string;
};

export type CloudUploadProgress = {
  file_id: number;
  chunk_count: number;
  received_chunks: number;
  synced_chunks: number;
  received_indices: number[];
  synced_indices: number[];
  upload_status: string;
};

export type CloudFilesLimits = {
  max_upload_bytes: number;
  chunk_size_bytes: number;
};

export type CloudStorageStatus = {
  storage_backend: string;
  discord_configured: boolean;
  bandwidth_limit_mbps?: number;
  max_upload_bytes?: number;
  chunk_size_bytes?: number;
  discord_ok: boolean;
  bot_count?: number;
  bots_ok?: number;
  bots?: Array<{ index: number; ok: boolean; username?: string; error?: string; in_cooldown?: boolean }>;
  bot_username?: string | null;
  channel_name?: string | null;
  discord_error?: string | null;
  api_features?: string[];
  discord_check_pending?: boolean;
};

const SESSION_FLAG = "ch_logged";
const LEGACY_TOKEN_KEY = "token";

function wipeLegacyJwt(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    /* ignore quota / private mode */
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  wipeLegacyJwt();
  return localStorage.getItem(SESSION_FLAG);
}

export function setToken(_token?: string) {
  wipeLegacyJwt();
  localStorage.setItem(SESSION_FLAG, "1");
}

export function clearToken() {
  wipeLegacyJwt();
  localStorage.removeItem(SESSION_FLAG);
  clearStepUpToken();
}

function formatApiError(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const field = Array.isArray(item.loc) ? item.loc.at(-1) : null;
          const msg = String(item.msg);
          if (
            field === "hostname" ||
            /match pattern|string should match/i.test(msg)
          ) {
            return (
              "O hostname só pode ter letras sem acento, números e hífen. " +
              "Não use espaços, ç, ã, é nem outros caracteres especiais. " +
              "Exemplo: meu-servidor"
            );
          }
          return field ? `${field}: ${msg}` : msg;
        }
        return "Dados inválidos";
      })
      .join("; ");
  }
  return "Erro na requisição";
}

async function uploadRequest<T>(
  path: string,
  formData: FormData,
  signal?: AbortSignal
): Promise<T> {
  const session = !!getToken();
  const headers: Record<string, string> = {};

  if (isCloudPath(path)) {
    cloudApiLog("-->", "POST", path, { session: session ? "sim" : "NÃO" });
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers,
      body: formData,
      signal,
      credentials: "include",
    });
  } catch (e) {
    if (isCloudPath(path)) cloudApiLog("FALHA REDE", "POST", path, e);
    throw e;
  }

  if (isCloudPath(path)) {
    cloudApiLog("<--", "POST", path, { status: res.status, ok: res.ok });
  }

  if (res.status === 401) {
    clearToken();
  }
  if (!res.ok) {
    if (res.status === 413) {
      throw new Error("Fragmento rejeitado pelo proxy (muito grande). Tente novamente.");
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err.detail) || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_URL}/api/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then((res) => res.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

let financeRefreshInFlight: Promise<boolean> | null = null;

type RequestOptions = RequestInit & { _retried?: boolean; _stepUpRetried?: boolean };

async function tryRefreshFinanceSession(): Promise<boolean> {
  if (!financeRefreshInFlight) {
    financeRefreshInFlight = fetch(`${API_URL}/api/finance/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then((res) => res.ok)
      .catch(() => false)
      .finally(() => {
        financeRefreshInFlight = null;
      });
  }
  return financeRefreshInFlight;
}

async function financeRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...options, headers, credentials: "include" });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro de rede";
    if (msg === "Failed to fetch") {
      throw new Error(
        `Não foi possível contactar a API (${API_URL}). Verifique se o backend está rodando.`
      );
    }
    throw e;
  }

  const skipRefresh =
    path.includes("/api/finance/auth/login") ||
    path.includes("/api/finance/auth/refresh") ||
    path.includes("/api/finance/auth/logout") ||
    path.includes("/api/finance/auth/register") ||
    path.includes("/api/finance/auth/mfa");

  if (res.status === 401 && !options._retried && !skipRefresh) {
    const refreshed = await tryRefreshFinanceSession();
    if (refreshed) {
      return financeRequest<T>(path, { ...options, _retried: true });
    }
    clearFinanceToken();
  } else if (res.status === 401) {
    clearFinanceToken();
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err.detail) || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const session = !!getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  const cachedStepUp = peekStepUpToken();
  if (cachedStepUp && !headers["X-Step-Up-Token"]) {
    headers["X-Step-Up-Token"] = cachedStepUp;
  }

  const method = (options.method || "GET").toUpperCase();
  if (isCloudPath(path)) {
    let bodyPreview: unknown;
    if (options.body) {
      try {
        bodyPreview = JSON.parse(String(options.body));
      } catch {
        bodyPreview = String(options.body).slice(0, 200);
      }
    }
    cloudApiLog("-->", method, path, {
      session: session ? "sim" : "NÃO",
      body: bodyPreview,
    });
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...options, headers, credentials: "include" });
  } catch (e) {
    if (isCloudPath(path)) cloudApiLog("FALHA REDE", method, path, e);
    const msg = e instanceof Error ? e.message : "Erro de rede";
    if (msg === "Failed to fetch") {
      throw new Error(
        `Não foi possível contactar a API (${API_URL}). Verifique se o backend está rodando.`
      );
    }
    throw e;
  }

  if (isCloudPath(path)) {
    cloudApiLog("<--", method, path, { status: res.status, ok: res.ok });
  }

  const skipRefresh =
    path.includes("/api/auth/login") ||
    path.includes("/api/auth/refresh") ||
    path.includes("/api/auth/logout") ||
    path.includes("/api/auth/passkey/login");

  if (res.status === 401 && !options._retried && !skipRefresh) {
    const refreshed = await tryRefreshSession();
    if (refreshed) {
      return request<T>(path, { ...options, _retried: true });
    }
    clearToken();
  } else if (res.status === 401) {
    clearToken();
  }

  const skipStepUp =
    path.includes("/api/auth/step-up") ||
    path.includes("/api/auth/login") ||
    path.includes("/api/auth/mfa");

  if (res.status === 403 && !options._stepUpRetried && !skipStepUp) {
    const err = await res.json().catch(() => ({ detail: null }));
    const detail = err?.detail;
    const stepUpHeader = res.headers.get("X-Step-Up-Required") === "1";
    const stepUpBody =
      detail &&
      typeof detail === "object" &&
      "code" in detail &&
      (detail as { code?: string }).code === "step_up_required";
    if (stepUpHeader || stepUpBody) {
      const mfaEnabled =
        detail && typeof detail === "object" && "mfa_enabled" in detail
          ? Boolean((detail as { mfa_enabled?: boolean }).mfa_enabled)
          : false;
      const token = await ensureStepUp(mfaEnabled);
      return request<T>(path, {
        ...options,
        headers: { ...headers, "X-Step-Up-Token": token },
        _stepUpRetried: true,
      });
    }
    throw new Error(formatApiError(detail) || res.statusText);
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err.detail) || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function downloadBlob(
  path: string,
  onProgress?: (loaded: number, total: number | null) => void,
  signal?: AbortSignal
): Promise<Blob> {
  const session = !!getToken();
  const headers: Record<string, string> = {};

  if (isCloudPath(path)) {
    cloudApiLog("-->", "GET", path, { session: session ? "sim" : "NÃO", download: true });
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { headers, signal, credentials: "include" });
  } catch (e) {
    if (isCloudPath(path)) cloudApiLog("FALHA REDE", "GET", path);
    if (signal?.aborted) throw e;
    throw new Error(
      "Falha na conexão. Arquivos grandes podem demorar — aguarde ou tente novamente."
    );
  }

  if (isCloudPath(path)) {
    cloudApiLog("<--", "GET", path, { status: res.status, ok: res.ok });
  }
  if (res.status === 401) {
    clearToken();
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err.detail) || res.statusText);
  }

  if (!onProgress || !res.body) {
    return res.blob();
  }

  const totalHeader = res.headers.get("Content-Length");
  const total = totalHeader ? Number.parseInt(totalHeader, 10) : null;
  const reader = res.body.getReader();
  const chunks: BlobPart[] = [];
  let loaded = 0;

  onProgress(0, total);

  while (true) {
    if (signal?.aborted) {
      await reader.cancel().catch(() => undefined);
      throw new DOMException("Aborted", "AbortError");
    }
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loaded += value.byteLength;
    onProgress(loaded, total);
  }

  const mimeType = res.headers.get("Content-Type") ?? undefined;
  return new Blob(chunks, mimeType ? { type: mimeType } : undefined);
}

export type SupportTicketStatus = "open" | "accepted" | "closed";

export type SupportStaff = {
  id: number;
  name: string;
};

export type SupportMessage = {
  id: number;
  author_id: number | null;
  author_name: string;
  author_is_admin: boolean;
  body: string;
  is_system: boolean;
  mentioned_user_ids: number[];
  created_at: string;
};

export type SupportTicket = {
  id: number;
  subject: string;
  status: SupportTicketStatus;
  user_id: number;
  user_name: string;
  accepted_by_id: number | null;
  accepted_by_name: string | null;
  last_message_preview: string;
  last_message_at: string;
  created_at: string;
  waiting_on_staff: boolean;
};

export type SupportTicketDetail = SupportTicket & {
  messages: SupportMessage[];
};

export type FinanceKind = "income" | "expense";

export type FinanceCategoryOption = {
  id: string;
  label: string;
};

export type FinanceMeta = {
  income_categories: FinanceCategoryOption[];
  expense_categories: FinanceCategoryOption[];
  event_categories: FinanceCategoryOption[];
  payment_methods: FinanceCategoryOption[];
  vapid_public_key?: string | null;
  push_available?: boolean;
};

export type FinanceTransaction = {
  id: number;
  kind: FinanceKind;
  title: string;
  amount_cents: number;
  category: string;
  payment_method: string;
  notes: string;
  occurred_on: string;
  receipt_ext?: string | null;
  has_receipt?: boolean;
  created_at: string;
  updated_at: string;
};

export type FinanceEventItem = {
  id: number;
  title: string;
  category: string;
  notes: string;
  starts_at: string;
  duration_min: number;
  all_day: boolean;
  created_at: string;
  updated_at: string;
};

export type FinanceMonthPoint = {
  year: number;
  month: number;
  label: string;
  income_cents: number;
  expense_cents: number;
  balance_cents: number;
};

export type FinanceCategoryTotal = {
  id: string;
  label: string;
  amount_cents: number;
  kind: FinanceKind;
};

export type FinanceStats = {
  income_cents: number;
  expense_cents: number;
  balance_cents: number;
  all_time_balance_cents: number;
  transaction_count: number;
  avg_daily_expense_cents: number;
  month_label: string;
  months: FinanceMonthPoint[];
  by_category: FinanceCategoryTotal[];
  upcoming_events: FinanceEventItem[];
};

export type FinanceTransactionPayload = {
  kind: FinanceKind;
  title: string;
  amount_cents: number;
  category: string;
  payment_method: string;
  notes: string;
  occurred_on: string;
};

export type FinanceGoalKind = "savings" | "monthly";

export type FinanceGoal = {
  id: number;
  title: string;
  kind: FinanceGoalKind;
  target_cents: number;
  saved_cents: number;
  remaining_cents: number;
  progress_percent: number;
  due_day: number | null;
  due_on: string | null;
  days_left: number | null;
  deadline: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
};

export type FinanceGoalPayload = {
  title: string;
  kind: FinanceGoalKind;
  target_cents: number;
  saved_cents: number;
  due_day?: number | null;
  deadline?: string | null;
  notes: string;
};

export type FinanceEventPayload = {
  title: string;
  category: string;
  notes: string;
  starts_at: string;
  duration_min: number;
  all_day: boolean;
};

export const api = {
  register: (data: {
    phone: string;
    email: string;
    name: string;
    password: string;
    whatsapp_ticket?: string;
    whatsapp_code?: string;
    email_ticket?: string;
    email_code?: string;
  }) => request<User>("/api/auth/register", { method: "POST", body: JSON.stringify(data) }),

  phoneVerification: () => request<PhoneVerificationStatus>("/api/auth/phone-verification"),

  sendWhatsAppCode: (phone: string) =>
    request<WhatsAppSendResult>("/api/auth/whatsapp/send", {
      method: "POST",
      body: JSON.stringify({ phone }),
    }),

  sendWhatsAppCodeProfile: (phone: string) =>
    request<WhatsAppSendResult>("/api/auth/whatsapp/send-profile", {
      method: "POST",
      body: JSON.stringify({ phone }),
    }),

  emailVerification: () => request<PhoneVerificationStatus>("/api/auth/email-verification"),

  sendEmailCode: (email: string) =>
    request<WhatsAppSendResult>("/api/auth/email/send", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  sendEmailCodeProfile: (email: string) =>
    request<WhatsAppSendResult>("/api/auth/email/send-profile", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  login: async (identifier: string, password: string) => {
    const trimmed = identifier.trim();
    const username = trimmed.includes("@") ? trimmed.toLowerCase() : trimmed.replace(/\D/g, "");
    const body = new URLSearchParams({ username, password });
    let res: Response;
    try {
      res = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
        credentials: "include",
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erro de rede";
      throw new Error(
        msg === "Failed to fetch"
          ? "Não foi possível contactar o servidor. Verifique sua conexão ou tente novamente."
          : msg
      );
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Telefone, e-mail ou senha incorretos" }));
      throw new Error(formatApiError(err.detail) || "Telefone, e-mail ou senha incorretos");
    }
    return res.json() as Promise<LoginResult>;
  },

  verifyMfa: (ticket: string, code: string) =>
    request<LoginResult>("/api/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ ticket, code }),
    }),

  mfaSetupStart: (password: string) =>
    request<MfaSetupStart>("/api/auth/mfa/setup/start", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  mfaSetupConfirm: (ticket: string, code: string) =>
    request<User>("/api/auth/mfa/setup/confirm", {
      method: "POST",
      body: JSON.stringify({ ticket, code }),
    }),

  mfaDisable: (password: string, code: string) =>
    request<User>("/api/auth/mfa/disable", {
      method: "POST",
      body: JSON.stringify({ password, code }),
    }),

  stepUp: (password: string, mfa_code?: string) =>
    request<StepUpResult>("/api/auth/step-up", {
      method: "POST",
      body: JSON.stringify({ password, mfa_code: mfa_code || null }),
    }),

  authSessions: () => request<AuthSessionItem[]>("/api/auth/sessions"),

  revokeAuthSession: (id: number) =>
    request<void>(`/api/auth/sessions/${id}`, { method: "DELETE" }),

  revokeOtherAuthSessions: () =>
    request<{ revoked: number }>("/api/auth/sessions/revoke-others", { method: "POST" }),

  passkeyRegisterOptions: () =>
    request<Record<string, unknown>>("/api/auth/passkey/register/options", {
      method: "POST",
    }),

  passkeyRegisterVerify: (credential: unknown, device_name?: string) =>
    request<PasskeyItem>("/api/auth/passkey/register/verify", {
      method: "POST",
      body: JSON.stringify({ credential, device_name }),
    }),

  passkeyLoginOptions: (username: string) =>
    request<Record<string, unknown>>("/api/auth/passkey/login/options", {
      method: "POST",
      body: JSON.stringify({ username }),
    }),

  passkeyLoginVerify: (username: string, credential: unknown) =>
    request<LoginResult>("/api/auth/passkey/login/verify", {
      method: "POST",
      body: JSON.stringify({ username, credential }),
    }),

  listPasskeys: () => request<PasskeyItem[]>("/api/auth/passkeys"),

  deletePasskey: (id: number) =>
    request<void>(`/api/auth/passkeys/${id}`, { method: "DELETE" }),

  logout: () => request<void>("/api/auth/logout", { method: "POST" }),

  me: () => request<User>("/api/auth/me"),

  updateProfile: (data: {
    name: string;
    email: string;
    phone: string;
    current_password: string;
    new_password?: string;
    whatsapp_ticket?: string;
    whatsapp_code?: string;
    email_ticket?: string;
    email_code?: string;
  }) => request<User>("/api/auth/me", { method: "PATCH", body: JSON.stringify(data) }),

  osTemplates: () => request<OsTemplateOption[]>("/api/vps/os-templates"),

  plans: () =>
    request<
      Array<{
        id: number;
        slug: string;
        name: string;
        description: string;
        min_vcpu: number;
        max_vcpu: number;
        min_ram_mb: number;
        max_ram_mb: number;
        network_mbps: number;
        default_disk_gb: number;
        max_disk_gb: number;
        price_per_vcpu_cents: number;
        price_per_gb_ram_cents: number;
        price_per_gb_disk_cents: number;
      }>
    >("/api/vps/plans"),

  presets: (planSlug?: string) =>
    request<
      Array<{
        id: number;
        plan_id: number;
        slug: string;
        name: string;
        vcpu: number;
        ram_mb: number;
        disk_gb: number;
        price_cents: number;
        is_popular: boolean;
        sort_order: number;
        cloud_bonus_gb?: number;
      }>
    >(planSlug ? `/api/vps/presets?plan_slug=${planSlug}` : "/api/vps/presets"),

  quote: (data: {
    plan_id: number;
    vcpu: number;
    ram_mb: number;
    disk_gb: number;
    preset_id?: number | null;
    coupon_code?: string | null;
    os_template?: string;
  }) =>
    request<{
      subtotal_cents: number;
      discount_cents: number;
      total_cents: number;
      monthly_cents: number;
      coupon_code: string | null;
      warnings: string[];
      os_template: string;
    }>("/api/vps/quote", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  createOrder: (data: {
    plan_id: number;
    preset_id?: number;
    vcpu: number;
    ram_mb: number;
    disk_gb: number;
    hostname: string;
    coupon_code?: string;
    os_template?: string;
  }) => request("/api/orders", { method: "POST", body: JSON.stringify(data) }),

  order: (id: number) => request<VpsOrder>(`/api/orders/${id}`),

  upgradeQuote: (
    instanceId: number,
    data: {
      target_vcpu: number;
      target_ram_mb: number;
      target_disk_gb: number;
      preset_id?: number | null;
    }
  ) =>
    request<{
      current_vcpu: number;
      current_ram_mb: number;
      current_disk_gb: number;
      target_vcpu: number;
      target_ram_mb: number;
      target_disk_gb: number;
      total_cents: number;
      monthly_delta_cents: number;
      current_monthly_cents: number;
      new_monthly_cents: number;
      days_remaining: number;
      period_days: number;
      prorated: boolean;
      paid_until?: string | null;
    }>(`/api/vps/instances/${instanceId}/upgrade/quote`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  createUpgrade: (
    instanceId: number,
    data: {
      target_vcpu: number;
      target_ram_mb: number;
      target_disk_gb: number;
      preset_id?: number | null;
    }
  ) =>
    request<{
      id: number;
      status: string;
      payment_checkout_url: string | null;
      pix_br_code?: string | null;
      pix_qr_base64?: string | null;
      pix_expires_at?: string | null;
    }>(`/api/vps/instances/${instanceId}/upgrade`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  renewQuote: (instanceId: number, months: number) =>
    request<{
      months: number;
      monthly_cents: number;
      subtotal_cents: number;
      discount_cents: number;
      discount_percent: number;
      total_cents: number;
      paid_until: string;
      new_paid_until: string;
    }>(`/api/vps/instances/${instanceId}/renew/quote`, {
      method: "POST",
      body: JSON.stringify({ months }),
    }),

  createRenewal: (instanceId: number, months: number) =>
    request<{
      id: number;
      status: string;
      payment_checkout_url: string | null;
      pix_br_code?: string | null;
      pix_qr_base64?: string | null;
      pix_expires_at?: string | null;
    }>(`/api/vps/instances/${instanceId}/renew`, {
      method: "POST",
      body: JSON.stringify({ months }),
    }),

  syncOrderPayment: (id: number) =>
    request<VpsOrder>(`/api/orders/${id}/sync-payment`, { method: "POST" }),

  retryOrderCheckout: (id: number) =>
    request<{
      id: number;
      status: string;
      payment_checkout_url: string | null;
      pix_br_code?: string | null;
      pix_qr_base64?: string | null;
      pix_expires_at?: string | null;
      total_cents?: number;
    }>(`/api/orders/${id}/retry-checkout`, { method: "POST" }),

  orders: () => request<VpsOrder[]>("/api/orders"),

  deleteOrder: (id: number) => request<void>(`/api/orders/${id}`, { method: "DELETE" }),

  paymentConfig: () =>
    request<{
      payments_required: boolean;
      provider: string;
      skip_payment_for_testing: boolean;
      cloud_max_upload_bytes?: number;
      cloud_max_upload_gb?: number;
      cloud_chunk_size_bytes?: number;
    }>("/api/payments/config"),

  gameTypes: () => request<GameTypeInfo[]>("/api/game-servers/types"),

  gamePresets: (gameType?: string) =>
    request<GamePreset[]>(
      gameType ? `/api/game-servers/presets?game_type=${gameType}` : "/api/game-servers/presets"
    ),

  gameQuote: (data: { game_type: string; preset_id: number }) =>
    request<{
      game_type: string;
      preset_id: number;
      slots: number;
      ram_mb: number;
      total_cents: number;
      monthly_cents: number;
    }>("/api/game-servers/quote", { method: "POST", body: JSON.stringify(data) }),

  createGameOrder: (data: { game_type: string; preset_id: number; server_name: string }) =>
    request<GameOrder>("/api/game-orders", { method: "POST", body: JSON.stringify(data) }),

  gameOrder: (id: number) => request<GameOrder>(`/api/game-orders/${id}`),

  gameOrders: () => request<GameOrder[]>("/api/game-orders"),

  deleteGameOrder: (id: number) =>
    request<void>(`/api/game-orders/${id}`, { method: "DELETE" }),

  syncGameOrderPayment: (id: number) =>
    request<GameOrder>(`/api/game-orders/${id}/sync-payment`, { method: "POST" }),

  retryGameCheckout: (id: number) =>
    request<GameOrder>(`/api/game-orders/${id}/retry-checkout`, { method: "POST" }),

  confirmGameOrderPayment: (id: number) =>
    request<GameOrder>(`/api/game-orders/${id}/confirm-payment`, { method: "POST" }),

  gameServers: () => request<GameServer[]>("/api/game-servers/instances"),

  gameServer: (id: number) => request<GameServer>(`/api/game-servers/instances/${id}`),

  startGameServer: (id: number) =>
    request<{ status: string; pid: number }>(`/api/game-servers/instances/${id}/start`, {
      method: "POST",
    }),

  stopGameServer: (id: number) =>
    request<{ status: string }>(`/api/game-servers/instances/${id}/stop`, { method: "POST" }),

  restartGameServer: (id: number) =>
    request<{ status: string; pid: number }>(`/api/game-servers/instances/${id}/restart`, {
      method: "POST",
    }),

  gameServerLogs: (id: number, tail = 100) =>
    request<{ lines: string; tail: number }>(
      `/api/game-servers/instances/${id}/logs?tail=${tail}`
    ),

  gameServerFiles: (id: number, path = "") =>
    request<GameFileEntry[]>(
      `/api/game-servers/instances/${id}/files${path ? `?path=${encodeURIComponent(path)}` : ""}`
    ),

  gameServerFileContent: (id: number, path: string) =>
    request<{ path: string; content: string }>(
      `/api/game-servers/instances/${id}/files/content?path=${encodeURIComponent(path)}`
    ),

  saveGameServerFile: (id: number, path: string, content: string) =>
    request<{ ok: boolean }>(`/api/game-servers/instances/${id}/files/content`, {
      method: "PUT",
      body: JSON.stringify({ path, content }),
    }),

  webPresets: () => request<WebPreset[]>("/api/web-sites/presets"),

  webHostingDns: () => request<{ dns_target: string }>("/api/web-sites/hosting-dns"),

  webQuote: (data: { preset_id: number; coupon_code?: string | null }) =>
    request<{
      preset_id: number;
      ram_mb: number;
      disk_mb: number;
      cpu_percent: number;
      php_enabled: boolean;
      subtotal_cents: number;
      discount_cents: number;
      total_cents: number;
      monthly_cents: number;
      coupon_code?: string | null;
    }>("/api/web-sites/quote", { method: "POST", body: JSON.stringify(data) }),

  createWebOrder: (data: {
    preset_id: number;
    site_slug: string;
    domain?: string | null;
    coupon_code?: string | null;
  }) =>
    request<WebOrder>("/api/web-orders", { method: "POST", body: JSON.stringify(data) }),

  webOrder: (id: number) => request<WebOrder>(`/api/web-orders/${id}`),

  webOrders: () => request<WebOrder[]>("/api/web-orders"),

  deleteWebOrder: (id: number) => request<void>(`/api/web-orders/${id}`, { method: "DELETE" }),

  syncWebOrderPayment: (id: number) =>
    request<WebOrder>(`/api/web-orders/${id}/sync-payment`, { method: "POST" }),

  retryWebCheckout: (id: number) =>
    request<WebOrder>(`/api/web-orders/${id}/retry-checkout`, { method: "POST" }),

  webSites: () => request<WebSite[]>("/api/web-sites/instances"),

  webSite: (id: number) => request<WebSite>(`/api/web-sites/instances/${id}`),

  webSiteRenewQuote: (siteId: number, months: number) =>
    request<{
      months: number;
      monthly_cents: number;
      subtotal_cents: number;
      discount_cents: number;
      discount_percent: number;
      total_cents: number;
      paid_until: string;
      new_paid_until: string;
    }>(`/api/web-sites/instances/${siteId}/renew/quote`, {
      method: "POST",
      body: JSON.stringify({ months }),
    }),

  webSiteCreateRenewal: (siteId: number, months: number) =>
    request<WebOrder>(`/api/web-sites/instances/${siteId}/renew`, {
      method: "POST",
      body: JSON.stringify({ months }),
    }),

  webSitePageEditor: (id: number) =>
    request<WebPageEditor>(`/api/web-sites/instances/${id}/page`),

  saveWebSitePage: (id: number, config: WebPageConfig) =>
    request<WebPageEditor>(`/api/web-sites/instances/${id}/page`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),

  uploadWebSitePageAvatar: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return uploadRequest<WebPageEditor>(`/api/web-sites/instances/${id}/page/avatar`, form);
  },

  startWebSite: (id: number) =>
    request<WebSite>(`/api/web-sites/instances/${id}/start`, { method: "POST" }),

  stopWebSite: (id: number) =>
    request<WebSite>(`/api/web-sites/instances/${id}/stop`, { method: "POST" }),

  restartWebSite: (id: number) =>
    request<WebSite>(`/api/web-sites/instances/${id}/restart`, { method: "POST" }),

  updateWebSiteDomain: (id: number, domain: string | null) =>
    request<WebSite>(`/api/web-sites/instances/${id}/domain`, {
      method: "PUT",
      body: JSON.stringify({ domain }),
    }),

  refreshWebSiteSsl: (id: number) =>
    request<WebSite>(`/api/web-sites/instances/${id}/ssl/refresh`, { method: "POST" }),

  webSiteLogs: (id: number, tail = 100) =>
    request<{ lines: string; tail: number }>(`/api/web-sites/instances/${id}/logs?tail=${tail}`),

  webSiteAnalytics: (id: number, days = 30) =>
    request<WebSiteAnalytics>(`/api/web-sites/instances/${id}/analytics?days=${days}`),

  webSiteFiles: (id: number, path = "") =>
    request<GameFileEntry[]>(
      `/api/web-sites/instances/${id}/files${path ? `?path=${encodeURIComponent(path)}` : ""}`
    ),

  webSiteFileContent: (id: number, path: string) =>
    request<{ path: string; content: string }>(
      `/api/web-sites/instances/${id}/files/content?path=${encodeURIComponent(path)}`
    ),

  saveWebSiteFile: (id: number, path: string, content: string) =>
    request<{ ok: boolean }>(`/api/web-sites/instances/${id}/files/content`, {
      method: "PUT",
      body: JSON.stringify({ path, content }),
    }),

  createWebSiteFolder: (id: number, path: string, name: string) =>
    request<GameFileEntry>(`/api/web-sites/instances/${id}/files/mkdir`, {
      method: "POST",
      body: JSON.stringify({ path, name }),
    }),

  uploadWebSiteFile: (id: number, dir: string, file: File, relativePath?: string | null) => {
    const form = new FormData();
    const uploadName = (relativePath ?? file.name).replace(/\\/g, "/");
    form.append("file", file, uploadName);
    return uploadRequest<GameFileEntry>(
      `/api/web-sites/instances/${id}/files/upload?path=${encodeURIComponent(dir)}`,
      form
    );
  },

  deleteWebSiteFile: (id: number, path: string) =>
    request<{ ok: boolean }>(`/api/web-sites/instances/${id}/files?path=${encodeURIComponent(path)}`, {
      method: "DELETE",
    }),

  cloudFilesLimits: async () => {
    try {
      return await request<CloudFilesLimits>("/api/files/upload/limits");
    } catch {
      return request<CloudFilesLimits>("/api/files/limits");
    }
  },

  instances: () => request<VpsInstanceList[]>("/api/vps/instances"),

  instance: (id: number) => request<VpsInstanceDetail>(`/api/vps/instances/${id}`),

  instanceCredentials: (id: number) =>
    request<WindowsCredentials>(`/api/vps/instances/${id}/credentials`),

  setVpsConnectionDomain: (
    instanceId: number,
    data: { domain: string; public_port: number }
  ) =>
    request<VpsConnectionDomain>(`/api/vps/instances/${instanceId}/connections`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteVpsConnectionDomain: (instanceId: number, connectionId: number) =>
    request<void>(`/api/vps/instances/${instanceId}/connections/${connectionId}`, {
      method: "DELETE",
    }),

  instanceConsole: (id: number) => request<VpsConsoleInfo>(`/api/vps/instances/${id}/console`),

  instanceConsoleTicket: (id: number) =>
    request<VpsConsoleTicket>(`/api/vps/instances/${id}/console/ticket`, { method: "POST" }),

  instanceConsoleWsTicket: (id: number) =>
    request<VpsConsoleWsTicket>(`/api/vps/instances/${id}/console/ws-ticket`, { method: "POST" }),

  instancePowerOn: (id: number) =>
    request<{ success: boolean; message: string }>(`/api/vps/instances/${id}/power-on`, {
      method: "POST",
    }),

  instancePowerOff: (id: number) =>
    request<{ success: boolean; message: string }>(`/api/vps/instances/${id}/power-off`, {
      method: "POST",
    }),

  instanceReset: (id: number) =>
    request<{ success: boolean; message: string }>(`/api/vps/instances/${id}/reset`, {
      method: "POST",
    }),

  instanceDestroy: (id: number) =>
    request<{ success: boolean; message: string }>(`/api/vps/instances/${id}`, {
      method: "DELETE",
    }),

  adminCoupons: () => request<DiscountCoupon[]>("/api/admin/coupons"),

  adminNginxProxies: () => request<NginxProxyEntry[]>("/api/admin/nginx-proxies"),

  adminCreateNginxProxy: (data: {
    domain: string;
    mode: NginxProxyMode;
    upstream_url?: string;
    redirect_url?: string;
    include_www?: boolean;
    notes?: string;
  }) =>
    request<NginxProxyEntry>("/api/admin/nginx-proxies", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  adminUpdateNginxProxy: (
    id: number,
    data: Partial<{
      domain: string;
      mode: NginxProxyMode;
      upstream_url: string;
      redirect_url: string;
      include_www: boolean;
      notes: string;
    }>
  ) =>
    request<NginxProxyEntry>(`/api/admin/nginx-proxies/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  adminDeleteNginxProxy: (id: number) =>
    request<void>(`/api/admin/nginx-proxies/${id}`, { method: "DELETE" }),

  adminUpdateSystemNginxProxy: (kind: NginxProxyKind, referenceId: number, domain: string) =>
    request<NginxProxyEntry>(`/api/admin/nginx-proxies/system/${kind}/${referenceId}`, {
      method: "PUT",
      body: JSON.stringify({ domain }),
    }),

  adminDeleteSystemNginxProxy: (kind: NginxProxyKind, referenceId: number) =>
    request<void>(`/api/admin/nginx-proxies/system/${kind}/${referenceId}`, {
      method: "DELETE",
    }),

  adminCreateCoupon: (data: {
    code: string;
    description?: string;
    discount_percent?: number;
    discount_cents?: number;
    max_uses?: number;
    valid_from?: string;
    valid_until?: string;
    is_active?: boolean;
  }) =>
    request<DiscountCoupon>("/api/admin/coupons", { method: "POST", body: JSON.stringify(data) }),

  adminUpdateCoupon: (
    id: number,
    data: Partial<{
      description: string;
      discount_percent: number;
      discount_cents: number;
      max_uses: number;
      valid_from: string;
      valid_until: string;
      is_active: boolean;
    }>
  ) =>
    request<DiscountCoupon>(`/api/admin/coupons/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  adminUsers: () => request<User[]>("/api/admin/users"),

  adminCreateVps: (data: {
    user_id: number;
    hostname: string;
    os_template?: string;
    plan_id?: number | null;
    preset_id?: number | null;
    vcpu: number;
    ram_mb: number;
    disk_gb: number;
  }) =>
    request<VpsOrder>("/api/admin/vps", { method: "POST", body: JSON.stringify(data) }),

  adminCreateUser: (data: {
    phone: string;
    email: string;
    name: string;
    password: string;
    is_admin?: boolean;
  }) =>
    request<User>("/api/admin/users", { method: "POST", body: JSON.stringify(data) }),

  adminUpdateUser: (
    id: number,
    data: Partial<{
      name: string;
      is_active: boolean;
      is_admin: boolean;
      password: string;
      reset_mfa: boolean;
    }>
  ) =>
    request<User>(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  adminUserDetail: (id: number) =>
    request<AdminUserDetail>(`/api/admin/users/${id}/detail`),

  adminUserDeletionPreview: (id: number) =>
    request<AdminAccountDeletionPreview>(`/api/admin/users/${id}/deletion-preview`),

  adminDeleteUser: (id: number, confirm_phone: string) =>
    request<AdminAccountDeleteResult>(`/api/admin/users/${id}`, {
      method: "DELETE",
      body: JSON.stringify({ confirm_phone }),
    }),

  adminStats: (days: 7 | 30 | 90 = 30) =>
    request<AdminStats>(`/api/admin/stats?days=${days}`),

  adminAnalytics: (days: 7 | 30 | 90 = 30) =>
    request<AdminAnalytics>(`/api/admin/analytics?days=${days}`),

  adminDeleteOrder: (kind: string, orderId: number) =>
    request<void>(`/api/admin/orders/${encodeURIComponent(kind)}/${orderId}`, {
      method: "DELETE",
    }),

  adminDeleteWebSite: (siteId: number) =>
    request<{ site_id: number; message: string }>(`/api/admin/web-sites/${siteId}`, {
      method: "DELETE",
    }),

  adminWebSites: () => request<WebSiteAdmin[]>("/api/admin/web-sites"),

  adminWebSite: (id: number) => request<WebSiteAdminDetail>(`/api/admin/web-sites/${id}`),

  adminWebSitePageEditor: (id: number) =>
    request<WebPageEditor>(`/api/admin/web-sites/${id}/page`),

  adminSaveWebSitePage: (id: number, config: WebPageConfig) =>
    request<WebPageEditor>(`/api/admin/web-sites/${id}/page`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),

  adminUploadWebSitePageAvatar: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return uploadRequest<WebPageEditor>(`/api/admin/web-sites/${id}/page/avatar`, form);
  },

  adminStartWebSite: (id: number) =>
    request<WebSite>(`/api/admin/web-sites/${id}/start`, { method: "POST" }),

  adminStopWebSite: (id: number) =>
    request<WebSite>(`/api/admin/web-sites/${id}/stop`, { method: "POST" }),

  adminRestartWebSite: (id: number) =>
    request<WebSite>(`/api/admin/web-sites/${id}/restart`, { method: "POST" }),

  adminUpdateWebSiteDomain: (id: number, domain: string | null) =>
    request<WebSite>(`/api/admin/web-sites/${id}/domain`, {
      method: "PUT",
      body: JSON.stringify({ domain }),
    }),

  adminWebSiteLogs: (id: number, tail = 100) =>
    request<{ lines: string; tail: number }>(`/api/admin/web-sites/${id}/logs?tail=${tail}`),

  adminWebSiteAnalytics: (id: number, days = 30) =>
    request<WebSiteAnalytics>(`/api/admin/web-sites/${id}/analytics?days=${days}`),

  adminWebSiteFiles: (id: number, path?: string) =>
    request<GameFileEntry[]>(
      `/api/admin/web-sites/${id}/files${path ? `?path=${encodeURIComponent(path)}` : ""}`
    ),

  adminWebSiteFileContent: (id: number, path: string) =>
    request<{ path: string; content: string }>(
      `/api/admin/web-sites/${id}/files/content?path=${encodeURIComponent(path)}`
    ),

  adminSaveWebSiteFile: (id: number, path: string, content: string) =>
    request<{ ok: boolean }>(`/api/admin/web-sites/${id}/files/content`, {
      method: "PUT",
      body: JSON.stringify({ path, content }),
    }),

  adminCreateWebSiteFolder: (id: number, path: string, name: string) =>
    request<GameFileEntry>(`/api/admin/web-sites/${id}/files/mkdir`, {
      method: "POST",
      body: JSON.stringify({ path, name }),
    }),

  adminUploadWebSiteFile: (id: number, dir: string, file: File, relativePath?: string | null) => {
    const form = new FormData();
    form.append("file", file, relativePath || file.name);
    return request<GameFileEntry>(
      `/api/admin/web-sites/${id}/files/upload?path=${encodeURIComponent(dir)}`,
      { method: "POST", body: form }
    );
  },

  adminDeleteWebSiteFile: (id: number, path: string) =>
    request<{ ok: boolean }>(`/api/admin/web-sites/${id}/files?path=${encodeURIComponent(path)}`, {
      method: "DELETE",
    }),

  adminClearMachineError: (instanceId: number) =>
    request<void>(`/api/admin/instances/${instanceId}/error`, { method: "DELETE" }),

  adminUserFiles: (userId: number, parentId?: number | null) =>
    request<CloudFileItem[]>(
      parentId != null
        ? `/api/admin/users/${userId}/files?parent_id=${parentId}`
        : `/api/admin/users/${userId}/files`
    ),

  adminUserFileDownload: (userId: number, fileId: number, signal?: AbortSignal) =>
    downloadBlob(`/api/admin/users/${userId}/files/${fileId}/download`, undefined, signal),

  adminAdjustCloudQuota: (
    userId: number,
    data: { extra_gb: number; charge_mode: "no_charge" | "charge_now" | "defer_renewal"; note?: string }
  ) =>
    request<AdminCloudAdjustResult>(`/api/admin/users/${userId}/cloud-quota`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  adminUpdateVpsResources: (
    instanceId: number,
    data: {
      target_vcpu: number;
      target_ram_mb: number;
      target_disk_gb: number;
      charge_mode: "no_charge" | "charge_now" | "defer_renewal";
      apply_vmware?: boolean;
      paid_until?: string;
      clear_suspension?: boolean;
    }
  ) =>
    request<AdminVpsUpdateResult>(`/api/admin/instances/${instanceId}/resources`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  adminUpdateVpsBilling: (
    instanceId: number,
    data: {
      paid_until?: string;
      clear_suspension?: boolean;
      clear_pending_charge?: boolean;
      custom_monthly_cents?: number;
      clear_custom_monthly_cents?: boolean;
    }
  ) =>
    request<Record<string, unknown>>(`/api/admin/instances/${instanceId}/billing`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  adminUpdateCloudBilling: (
    userId: number,
    data: {
      paid_until?: string;
      cloud_contracted_gb?: number;
      cloud_monthly_cents?: number;
      clear_suspension?: boolean;
      clear_pending_charge?: boolean;
    }
  ) =>
    request<{ user_id: number; cloud: AdminCloudQuotaInfo }>(
      `/api/admin/users/${userId}/cloud-billing`,
      {
        method: "PATCH",
        body: JSON.stringify(data),
      }
    ),

  cloudStorageQuote: (packageSlug: string) =>
    request<CloudStorageQuote>(`/api/files/storage/packages/${encodeURIComponent(packageSlug)}/quote`),

  adminPixdevRelease: (text: string) =>
    request<PixDevResponse>("/api/admin/pixdev", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  adminInstances: () => request<VpsInstanceAdmin[]>("/api/admin/instances"),

  adminInstance: (id: number) => request<VpsInstanceAdminDetail>(`/api/admin/instances/${id}`),

  adminInstanceCredentials: (id: number) =>
    request<WindowsCredentials>(`/api/admin/instances/${id}/credentials`),

  adminInstancePowerOn: (id: number) =>
    request<{ success: boolean; message: string }>(`/api/admin/instances/${id}/power-on`, {
      method: "POST",
    }),

  adminInstancePowerOff: (id: number) =>
    request<{ success: boolean; message: string }>(`/api/admin/instances/${id}/power-off`, {
      method: "POST",
    }),

  adminInstanceReset: (id: number) =>
    request<{ success: boolean; message: string }>(`/api/admin/instances/${id}/reset`, {
      method: "POST",
    }),

  adminInstanceChangeIp: (id: number, ip_address: string) =>
    request<{ success: boolean; message: string }>(`/api/admin/instances/${id}/change-ip`, {
      method: "POST",
      body: JSON.stringify({ ip_address }),
    }),

  adminInstanceChangePassword: (id: number, username: string, new_password: string) =>
    request<{ success: boolean; message: string }>(
      `/api/admin/instances/${id}/change-password`,
      {
        method: "POST",
        body: JSON.stringify({ username, new_password }),
      }
    ),

  adminInstanceDestroy: (id: number) =>
    request<{ success: boolean; message: string }>(`/api/admin/instances/${id}`, {
      method: "DELETE",
    }),

  vmwareHealth: () => request<Record<string, unknown>>("/api/vmware/health"),

  adminDiscoverVms: () =>
    request<{
      template_name: string;
      unregistered: Array<{
        vm_name: string;
        hostname: string;
        suggested_name: string;
        vcpu: number;
        ram_mb: number;
        disk_gb: number;
        ip_address: string | null;
        power_state: string;
        suggested_plan_slug: string;
      }>;
      already_registered: string[];
      skipped: Array<{ vm_name: string; reason: string }>;
    }>("/api/admin/import/discover"),

  adminImportVms: (data: {
    vms: Array<{
      vm_name: string;
      user_id: number;
      plan_slug?: string;
    }>;
  }) =>
    request<{
      imported: Array<{
        vm_name: string;
        user_id: number;
        instance_id: number;
        phone: string;
        name: string;
        email?: string | null;
        plan_slug: string;
      }>;
      errors: Array<{ vm_name: string; error: string }>;
    }>("/api/admin/import", { method: "POST", body: JSON.stringify(data) }),

  adminHostInfo: () =>
    request<{
      roots: string[];
      max_edit_bytes: number;
      max_upload_bytes: number;
      shell_available: boolean;
      shell_cwd: string;
    }>("/api/admin/host/info"),

  adminHostFiles: (path = "") =>
    request<HostFileList>(`/api/admin/host/files?path=${encodeURIComponent(path)}`),

  adminHostFileContent: (path: string) =>
    request<HostFileContent>(`/api/admin/host/files/content?path=${encodeURIComponent(path)}`),

  adminHostFileWrite: (path: string, content: string) =>
    request<{ path: string; size: number }>("/api/admin/host/files/content", {
      method: "PUT",
      body: JSON.stringify({ path, content }),
    }),

  adminHostMkdir: (path: string, name: string) =>
    request<HostFileEntry>("/api/admin/host/files/mkdir", {
      method: "POST",
      body: JSON.stringify({ path, name }),
    }),

  adminHostCreateFile: (path: string, name: string) =>
    request<HostFileEntry>("/api/admin/host/files/create", {
      method: "POST",
      body: JSON.stringify({ path, name }),
    }),

  adminHostRename: (path: string, new_name: string) =>
    request<HostFileEntry>("/api/admin/host/files/rename", {
      method: "POST",
      body: JSON.stringify({ path, new_name }),
    }),

  adminHostDelete: (path: string) =>
    request<{ ok: boolean }>(`/api/admin/host/files?path=${encodeURIComponent(path)}`, {
      method: "DELETE",
    }),

  adminHostDownload: (path: string) =>
    downloadBlob(`/api/admin/host/files/download?path=${encodeURIComponent(path)}`),

  adminHostUpload: (dir: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return uploadRequest<HostFileEntry>(
      `/api/admin/host/files/upload?path=${encodeURIComponent(dir)}`,
      form
    );
  },

  adminHostShellTicket: () =>
    request<HostShellTicket>("/api/admin/host/shell/ticket", { method: "POST" }),

  adminHostMetrics: () => request<HostMetrics>("/api/admin/host/metrics"),

  cloudQuota: () => request<CloudQuota>("/api/files/quota"),

  cloudStoragePackages: () =>
    request<CloudStoragePackage[]>("/api/files/storage/packages"),

  cloudStoragePurchase: (package_slug: string) =>
    request<CloudStoragePurchaseResult>("/api/files/storage/purchase", {
      method: "POST",
      body: JSON.stringify({ package_slug }),
    }),

  cloudStorageRenewQuote: (months: number) =>
    request<CloudStorageRenewQuote>("/api/files/storage/renew/quote", {
      method: "POST",
      body: JSON.stringify({ months }),
    }),

  cloudStorageRenew: (months: number) =>
    request<CloudStorageRenewResult>("/api/files/storage/renew", {
      method: "POST",
      body: JSON.stringify({ months }),
    }),

  cloudStorageSyncPending: () =>
    request<{
      credited_orders: number;
      credited_gb: number;
      quota_bytes: number;
      extra_bytes: number;
    }>("/api/files/storage/sync-pending", { method: "POST" }),

  cloudStorageSyncPayment: (orderId: number) =>
    request<{
      order_id: number;
      status: string;
      extra_gb: number;
      quota_bytes: number;
      extra_bytes: number;
      pix_br_code?: string | null;
      pix_qr_base64?: string | null;
      pix_expires_at?: string | null;
      total_cents?: number;
    }>(`/api/files/storage/orders/${orderId}/sync-payment`, { method: "POST" }),

  cloudStorageOrders: () =>
    request<CloudStorageOrder[]>("/api/files/storage/orders"),

  deleteCloudStorageOrder: (orderId: number) =>
    request<void>(`/api/files/storage/orders/${orderId}`, { method: "DELETE" }),

  cloudStorageStatus: () => request<CloudStorageStatus>("/api/files/storage/status"),

  cloudList: (parentId?: number | null) =>
    request<CloudFileItem[]>(
      parentId != null ? `/api/files?parent_id=${parentId}` : "/api/files"
    ),

  cloudCreateFolder: (data: { name: string; parent_id?: number | null }) =>
    request<CloudFileItem>("/api/files/folders", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  cloudUploadStart: (
    data: {
      name: string;
      parent_id?: number | null;
      size_bytes: number;
      total_chunks: number;
      mime_type?: string | null;
    },
    signal?: AbortSignal
  ) =>
    request<{ file_id: number; name: string; chunk_size_bytes: number; resumed?: boolean; renamed_from?: string | null }>(
      "/api/files/upload/start",
      {
        method: "POST",
        body: JSON.stringify(data),
        signal,
      }
    ),

  cloudUploadProgress: async (fileId: number, signal?: AbortSignal) => {
    const primary = `/api/files/progress/${fileId}`;
    try {
      return await request<CloudUploadProgress>(primary, { signal });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (!msg.includes("Not Found") && !msg.includes("não encontrado")) throw e;
      return request<CloudUploadProgress>(`/api/files/upload/${fileId}/progress`, { signal });
    }
  },

  cloudCleanupIncomplete: (parentId?: number | null) =>
    request<{ removed: number }>(
      parentId != null
        ? `/api/files/cleanup-incomplete?parent_id=${parentId}`
        : "/api/files/cleanup-incomplete",
      { method: "POST" }
    ),

  cloudSyncPending: (fileId: number, signal?: AbortSignal) =>
    request<void>(`/api/files/upload/${fileId}/sync-pending`, { method: "POST", signal }),

  cloudUploadChunk: (
    fileId: number,
    chunkIndex: number,
    blob: Blob,
    signal?: AbortSignal
  ) => {
    const form = new FormData();
    form.append("chunk_index", String(chunkIndex));
    form.append("chunk", blob, `chunk_${chunkIndex}`);
    return uploadRequest<void>(`/api/files/upload/${fileId}/chunk`, form, signal);
  },

  cloudUploadComplete: (fileId: number, signal?: AbortSignal) =>
    request<CloudFileItem>(`/api/files/upload/${fileId}/complete`, {
      method: "POST",
      signal,
    }),

  cloudDownload: (fileId: number, signal?: AbortSignal) =>
    downloadBlob(`/api/files/${fileId}/download`, undefined, signal),

  cloudDownloadWithProgress: (
    fileId: number,
    onProgress: (loaded: number, total: number | null) => void,
    signal?: AbortSignal
  ) => downloadBlob(`/api/files/${fileId}/download`, onProgress, signal),

  cloudDelete: (fileId: number) =>
    request<void>(`/api/files/${fileId}`, { method: "DELETE" }),

  cloudMove: (ids: number[], parentId: number | null) =>
    request<{ moved: number }>("/api/files/move", {
      method: "POST",
      body: JSON.stringify({ ids, parent_id: parentId }),
    }),

  supportTickets: () => request<SupportTicket[]>("/api/support/tickets"),

  supportCreateTicket: (data: { subject: string; body: string }) =>
    request<SupportTicketDetail>("/api/support/tickets", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  supportTicket: (id: number) => request<SupportTicketDetail>(`/api/support/tickets/${id}`),

  supportSendMessage: (id: number, body: string) =>
    request<SupportTicketDetail>(`/api/support/tickets/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),

  supportCloseTicket: (id: number) =>
    request<SupportTicketDetail>(`/api/support/tickets/${id}/close`, { method: "POST" }),

  adminSupportTickets: (includeClosed = false) =>
    request<SupportTicket[]>(
      `/api/admin/support/tickets${includeClosed ? "?include_closed=true" : ""}`
    ),

  adminSupportStaff: () => request<SupportStaff[]>("/api/admin/support/staff"),

  adminSupportTicket: (id: number) =>
    request<SupportTicketDetail>(`/api/admin/support/tickets/${id}`),

  adminSupportAccept: (id: number) =>
    request<SupportTicketDetail>(`/api/admin/support/tickets/${id}/accept`, { method: "POST" }),

  adminSupportSendMessage: (id: number, body: string, mentionIds: number[] = []) =>
    request<SupportTicketDetail>(`/api/admin/support/tickets/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ body, mention_ids: mentionIds }),
    }),

  adminSupportCloseTicket: (id: number) =>
    request<SupportTicketDetail>(`/api/admin/support/tickets/${id}/close`, { method: "POST" }),

  adminSupportDeleteTicket: (id: number) =>
    request<void>(`/api/admin/support/tickets/${id}`, { method: "DELETE" }),

  financeMeta: () => financeRequest<FinanceMeta>("/api/finance/meta"),

  financeLogin: async (phone: string, password: string) => {
    const body = new URLSearchParams();
    body.set("username", phone);
    body.set("password", password);
    const res = await fetch(`${API_URL}/api/finance/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Telefone, e-mail ou senha incorretos" }));
      throw new Error(formatApiError(err.detail) || "Telefone, e-mail ou senha incorretos");
    }
    return res.json() as Promise<LoginResult>;
  },

  financeRegister: (data: {
    phone: string;
    email: string;
    name: string;
    password: string;
  }) =>
    financeRequest<User>("/api/finance/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  financeVerifyMfa: (ticket: string, code: string) =>
    financeRequest<LoginResult>("/api/finance/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ ticket, code }),
    }),

  financeMe: () => financeRequest<User>("/api/finance/auth/me"),

  financeLogout: () =>
    financeRequest<{ ok: boolean }>("/api/finance/auth/logout", { method: "POST" }),

  financeStats: (months = 6) =>
    financeRequest<FinanceStats>(`/api/finance/stats?months=${months}`),

  financeTransactions: (params?: {
    start?: string;
    end?: string;
    kind?: FinanceKind;
    category?: string;
    payment_method?: string;
  }) => {
    const query = new URLSearchParams();
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
    if (params?.kind) query.set("kind", params.kind);
    if (params?.category) query.set("category", params.category);
    if (params?.payment_method) query.set("payment_method", params.payment_method);
    const suffix = query.toString() ? `?${query}` : "";
    return financeRequest<FinanceTransaction[]>(`/api/finance/transactions${suffix}`);
  },

  financeCreateTransaction: (data: FinanceTransactionPayload) =>
    financeRequest<FinanceTransaction>("/api/finance/transactions", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  financeUpdateTransaction: (id: number, data: Partial<FinanceTransactionPayload>) =>
    financeRequest<FinanceTransaction>(`/api/finance/transactions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  financeDeleteTransaction: (id: number) =>
    financeRequest<void>(`/api/finance/transactions/${id}`, { method: "DELETE" }),

  financeUploadReceipt: async (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_URL}/api/finance/transactions/${id}/receipt`, {
      method: "POST",
      body: form,
      credentials: "include",
    });
    if (res.status === 401) clearFinanceToken();
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatApiError(err.detail) || res.statusText);
    }
    return res.json() as Promise<FinanceTransaction>;
  },

  financeReceiptBlob: async (id: number) => {
    const res = await fetch(`${API_URL}/api/finance/transactions/${id}/receipt`, {
      credentials: "include",
    });
    if (res.status === 401) clearFinanceToken();
    if (!res.ok) throw new Error("Não foi possível abrir a nota fiscal");
    return res.blob();
  },

  financeDeleteReceipt: (id: number) =>
    financeRequest<FinanceTransaction>(`/api/finance/transactions/${id}/receipt`, { method: "DELETE" }),

  financeGoals: () => financeRequest<FinanceGoal[]>("/api/finance/goals"),

  financeCreateGoal: (data: FinanceGoalPayload) =>
    financeRequest<FinanceGoal>("/api/finance/goals", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  financeUpdateGoal: (id: number, data: Partial<FinanceGoalPayload>) =>
    financeRequest<FinanceGoal>(`/api/finance/goals/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  financeDepositGoal: (id: number, amount_cents: number) =>
    financeRequest<FinanceGoal>(`/api/finance/goals/${id}/deposit`, {
      method: "POST",
      body: JSON.stringify({ amount_cents }),
    }),

  financeDeleteGoal: (id: number) => financeRequest<void>(`/api/finance/goals/${id}`, { method: "DELETE" }),

  financeEvents: (params?: { start?: string; end?: string }) => {
    const query = new URLSearchParams();
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
    const suffix = query.toString() ? `?${query}` : "";
    return financeRequest<FinanceEventItem[]>(`/api/finance/events${suffix}`);
  },

  financeCreateEvent: (data: FinanceEventPayload) =>
    financeRequest<FinanceEventItem>("/api/finance/events", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  financeUpdateEvent: (id: number, data: Partial<FinanceEventPayload>) =>
    financeRequest<FinanceEventItem>(`/api/finance/events/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  financeDeleteEvent: (id: number) =>
    financeRequest<void>(`/api/finance/events/${id}`, { method: "DELETE" }),

  financePushSubscribe: (data: { endpoint: string; keys: { p256dh: string; auth: string } }) =>
    financeRequest<void>("/api/finance/push/subscribe", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  financePushUnsubscribe: (data: { endpoint: string; keys: { p256dh: string; auth: string } }) =>
    financeRequest<void>("/api/finance/push/unsubscribe", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  hostPushMeta: () =>
    request<{ vapid_public_key?: string | null; push_available?: boolean }>("/api/push/public-key"),

  hostPushSubscribe: (data: { endpoint: string; keys: { p256dh: string; auth: string } }) =>
    request<void>("/api/push/subscribe", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  hostPushUnsubscribe: (data: { endpoint: string; keys: { p256dh: string; auth: string } }) =>
    request<void>("/api/push/unsubscribe", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

export function formatPrice(cents: number): string {
  return (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
