"use client";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { CheckCircle2, Info, XCircle } from "lucide-react";
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getUserId, setUserId } from "@/lib/session";

type Meta = { scenario_date: string; disclaimer: string; user: any; pages: string[]; status: any; auth_mode?: string; last_run_at?: string | null };
type Ctx = { meta: Meta | null; users: any[]; switchUser: (id: string) => void; refreshMeta: () => void; metaError: any; detail: boolean; setDetail: (v: boolean) => void };
const UserCtx = createContext<Ctx>({ meta: null, users: [], switchUser: () => {}, refreshMeta: () => {}, metaError: null, detail: false, setDetail: () => {} });
export const useSession = () => useContext(UserCtx);

type Toast = { id: number; kind: "ok" | "err" | "info"; text: string };
const ToastCtx = createContext<(kind: Toast["kind"], text: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function Providers({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  // "Show details" mode: technical panels (model metrics, raw data) stay folded away unless switched on.
  const [detail, setDetailState] = useState(false);
  useEffect(() => { try { setDetailState(localStorage.getItem("rf.detail") === "1"); } catch {} }, []);
  const setDetail = (v: boolean) => { setDetailState(v); try { localStorage.setItem("rf.detail", v ? "1" : "0"); } catch {} };

  const refreshMeta = useCallback(async () => {
    try {
      const [m, u] = await Promise.all([api<Meta>("/meta"), api<any[]>("/users")]);
      setMeta(m);
      setUsers(u);
      setMetaError(null);
    } catch (e) {
      setMetaError(e);
    }
  }, []);

  useEffect(() => {
    refreshMeta();
    const t = setInterval(() => { if (!meta || metaError) refreshMeta(); }, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshMeta, !!meta, !!metaError]);

  const switchUser = (id: string) => {
    if (id === getUserId()) return;
    setUserId(id);
    refreshMeta();
  };

  const toast = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4800);
  }, []);

  return (
    <MotionConfig reducedMotion="user">
    <UserCtx.Provider value={{ meta, users, switchUser, refreshMeta, metaError, detail, setDetail }}>
      <ToastCtx.Provider value={toast}>
        {children}
        <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[360px] flex-col gap-2">
          <AnimatePresence>
            {toasts.map((t) => (
              <motion.div key={t.id} layout initial={{ opacity: 0, y: 12, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: 24, transition: { duration: 0.18 } }} transition={{ type: "spring", stiffness: 420, damping: 32 }}
                className="pointer-events-auto flex items-start gap-2.5 rounded-lg border border-line-strong bg-[#101010]/95 px-3.5 py-3 text-[13px] shadow-pop backdrop-blur">
                {t.kind === "ok" ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-ok-600" /> : t.kind === "err" ? <XCircle className="mt-0.5 h-4 w-4 text-bad-600" /> : <Info className="mt-0.5 h-4 w-4 text-ink-500" />}
                <span className="text-ink-900">{t.text}</span>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </ToastCtx.Provider>
    </UserCtx.Provider>
    </MotionConfig>
  );
}
