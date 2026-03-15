"use client";

import { useEffect } from "react";
import { useToast } from "@/components/ui/ToastProvider";

export function useToastFeedback({ error, clearError, notice, clearNotice }) {
  const toast = useToast();

  useEffect(() => {
    if (!error) return;
    toast.error(error);
    clearError?.();
  }, [clearError, error, toast]);

  useEffect(() => {
    if (!notice) return;
    toast.success(notice);
    clearNotice?.();
  }, [clearNotice, notice, toast]);

  return toast;
}
