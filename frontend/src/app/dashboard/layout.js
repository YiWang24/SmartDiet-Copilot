"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Header from "@/components/layout/Header";
import BottomNav from "@/components/layout/BottomNav";
import { hasAuthSession } from "@/lib/api";
import { ROUTES } from "@/lib/constants";

export default function DashboardLayout({ children }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!hasAuthSession()) {
      router.replace(`${ROUTES.auth}?mode=login`);
      return;
    }
    setReady(true);
  }, [router]);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-slate-500">
        Checking session...
      </div>
    );
  }

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-x-hidden bg-[linear-gradient(160deg,_#ecfdf5_0%,_#f7fdf9_40%,_#f0fdf4_100%)]">
      <Header variant="dashboard" />
      <main className="mx-auto flex w-full flex-1 flex-col p-6 pb-24">
        {children}
      </main>
      <BottomNav />
    </div>
  );
}
