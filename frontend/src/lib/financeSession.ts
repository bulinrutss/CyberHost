const FINANCE_SESSION_FLAG = "fin_logged";

export function getFinanceToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(FINANCE_SESSION_FLAG);
}

export function setFinanceToken(): void {
  localStorage.setItem(FINANCE_SESSION_FLAG, "1");
}

export function clearFinanceToken(): void {
  localStorage.removeItem(FINANCE_SESSION_FLAG);
}
