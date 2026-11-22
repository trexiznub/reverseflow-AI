"use client";

const KEY = "rf.user";
export const DEFAULT_USER = "U-RAHUL";

export function getUserId(): string {
  if (typeof window === "undefined") return DEFAULT_USER;
  try {
    return window.localStorage.getItem(KEY) || DEFAULT_USER;
  } catch {
    return DEFAULT_USER;
  }
}

export function setUserId(id: string) {
  try {
    window.localStorage.setItem(KEY, id);
  } catch {}
  window.dispatchEvent(new Event("rf-user-changed"));
}
