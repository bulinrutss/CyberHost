type StepUpListener = (open: boolean, mfaEnabled: boolean) => void;

type Pending = {
  resolve: (token: string) => void;
  reject: (err: Error) => void;
  mfaEnabled: boolean;
};

let cached: { token: string; expiresAt: number } | null = null;
let pending: Pending | null = null;
const listeners = new Set<StepUpListener>();

export function peekStepUpToken(): string | null {
  if (!cached) return null;
  if (Date.now() >= cached.expiresAt) {
    cached = null;
    return null;
  }
  return cached.token;
}

export function storeStepUpToken(token: string, expiresInSeconds: number): void {
  const skewMs = 15_000;
  cached = {
    token,
    expiresAt: Date.now() + Math.max(30, expiresInSeconds) * 1000 - skewMs,
  };
}

export function clearStepUpToken(): void {
  cached = null;
}

export function subscribeStepUp(listener: StepUpListener): () => void {
  listeners.add(listener);
  if (pending) listener(true, pending.mfaEnabled);
  return () => {
    listeners.delete(listener);
  };
}

function notify(open: boolean, mfaEnabled: boolean): void {
  listeners.forEach((listener) => listener(open, mfaEnabled));
}

/** Abre o modal (ou reutiliza token em cache) e devolve o token de step-up. */
export function ensureStepUp(mfaEnabled = false): Promise<string> {
  const existing = peekStepUpToken();
  if (existing) return Promise.resolve(existing);

  if (pending) {
    pending.mfaEnabled = pending.mfaEnabled || mfaEnabled;
    notify(true, pending.mfaEnabled);
    return new Promise((resolve, reject) => {
      const prev = pending!;
      pending = {
        mfaEnabled: prev.mfaEnabled,
        resolve: (token) => {
          prev.resolve(token);
          resolve(token);
        },
        reject: (err) => {
          prev.reject(err);
          reject(err);
        },
      };
    });
  }

  return new Promise((resolve, reject) => {
    pending = { resolve, reject, mfaEnabled };
    notify(true, mfaEnabled);
  });
}

export function completeStepUpPrompt(token: string, expiresInSeconds: number): void {
  storeStepUpToken(token, expiresInSeconds);
  const current = pending;
  pending = null;
  notify(false, false);
  current?.resolve(token);
}

export function cancelStepUpPrompt(reason = "Confirmação cancelada"): void {
  const current = pending;
  pending = null;
  notify(false, false);
  current?.reject(new Error(reason));
}
