"use client";

type Props = {
  value: string;
  onChange: (value: string) => void;
};

export function AdminSearchInput({ value, onChange }: Props) {
  return (
    <input
      type="search"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Nome, VPS, e-mail ou telefone"
      className="input-glass w-full"
      autoComplete="off"
      spellCheck={false}
      aria-label="Buscar por nome, VPS, e-mail ou telefone"
    />
  );
}
