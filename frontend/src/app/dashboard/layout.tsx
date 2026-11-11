"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { PageShell } from "@/components/ui/PageShell";
import { api, getToken } from "@/lib/api";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api
      .me()
      .then((user) => {
        if (user.is_admin) router.replace("/admin");
      })
      .catch(() => router.push("/login"));
  }, [router]);

  return (
    <PageShell wide>
      {children}
    </PageShell>
  );
}
