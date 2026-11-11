/** Logs no console do navegador (F12) para debug de arquivos na nuvem. */

function ts(): string {
  return new Date().toISOString().slice(11, 23);
}

export function cloudLog(event: string, detail?: unknown): void {
  const prefix = `[CloudFiles ${ts()}]`;
  if (detail !== undefined) {
    console.log(`${prefix} ${event}`, detail);
  } else {
    console.log(`${prefix} ${event}`);
  }
}

export function cloudWarn(event: string, detail?: unknown): void {
  const prefix = `[CloudFiles ${ts()}]`;
  if (detail !== undefined) {
    console.warn(`${prefix} ${event}`, detail);
  } else {
    console.warn(`${prefix} ${event}`);
  }
}

export function cloudError(event: string, detail?: unknown): void {
  const prefix = `[CloudFiles ${ts()}]`;
  if (detail !== undefined) {
    console.error(`${prefix} ${event}`, detail);
  } else {
    console.error(`${prefix} ${event}`);
  }
}
