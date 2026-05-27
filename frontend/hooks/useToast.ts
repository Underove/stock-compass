"use client";

import { useCallback, useEffect, useState } from "react";

export type ToastType = "success" | "error" | "info";

export type Toast = {
  id: number;
  type: ToastType;
  message: string;
};

type Listener = (toasts: Toast[]) => void;

let nextId = 1;
let toasts: Toast[] = [];
const listeners = new Set<Listener>();

function emit() {
  for (const fn of listeners) fn(toasts);
}

export function showToast(message: string, type: ToastType = "success", duration = 2400) {
  const id = nextId++;
  toasts = [...toasts, { id, type, message }];
  emit();
  setTimeout(() => {
    toasts = toasts.filter(t => t.id !== id);
    emit();
  }, duration);
  return id;
}

export function useToasts(): Toast[] {
  const [state, setState] = useState<Toast[]>(toasts);
  useEffect(() => {
    const fn: Listener = (next) => setState(next);
    listeners.add(fn);
    return () => { listeners.delete(fn); };
  }, []);
  return state;
}

export function useToast() {
  return useCallback(showToast, []);
}
