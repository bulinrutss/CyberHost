"use client";

import { useTheme } from "@/components/ThemeProvider";
import { SvgMoon, SvgSun } from "@/components/ui/svgs";

type Props = {
  variant?: "app" | "marketing";
};

export function ThemeToggle({ variant = "app" }: Props) {
  const { theme, toggleTheme } = useTheme();
  const buttonClass =
    variant === "marketing"
      ? "btn-ghost-marketing !p-2.5 !rounded-full"
      : "btn-ghost !p-2.5 !rounded-full";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={buttonClass}
      aria-label={theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro"}
      title={theme === "dark" ? "Tema claro" : "Tema escuro"}
    >
      {theme === "dark" ? (
        <SvgSun className="w-4 h-4" />
      ) : (
        <SvgMoon className="w-4 h-4" />
      )}
    </button>
  );
}
