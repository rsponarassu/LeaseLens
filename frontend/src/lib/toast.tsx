/**
 * Notification bars.
 *
 * Every asynchronous action in the app reports through here, so success and
 * failure are never invisible: a bar slides in, plays the matching tone, and
 * the same event is kept in a short log behind the bell icon. Errors stay
 * longer than successes and are announced with `role="alert"`.
 */

import { AnimatePresence, motion } from "framer-motion"
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import type { ReactNode } from "react"
import { useSound } from "./sound"

export type ToastKind = "success" | "error" | "info" | "warning"

export interface Toast {
  id: string
  kind: ToastKind
  title: string
  message: string
  createdAt: number
  duration: number
}

export interface NotificationEntry {
  id: string
  kind: ToastKind
  title: string
  message: string
  at: number
  read: boolean
}

interface ToastOptions {
  title?: string
  duration?: number
  /** Set false for silent background updates. */
  sound?: boolean
  /** Skip the bell log (used for transient hints). */
  log?: boolean
}

interface ToastValue {
  success: (message: string, options?: ToastOptions) => string
  error: (message: string, options?: ToastOptions) => string
  info: (message: string, options?: ToastOptions) => string
  warning: (message: string, options?: ToastOptions) => string
  dismiss: (id: string) => void
  notifications: NotificationEntry[]
  unreadCount: number
  markAllRead: () => void
  clearNotifications: () => void
}

const ToastContext = createContext<ToastValue | null>(null)

const DEFAULT_TITLE: Record<ToastKind, string> = {
  success: "Done",
  error: "Something went wrong",
  info: "Heads up",
  warning: "Check this",
}

const DEFAULT_DURATION: Record<ToastKind, number> = {
  success: 4_500,
  info: 5_000,
  warning: 6_500,
  error: 8_000,
}

const ICONS: Record<ToastKind, typeof Info> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const [notifications, setNotifications] = useState<NotificationEntry[]>([])
  const timers = useRef(new Map<string, number>())
  const { play } = useSound()

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      window.clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const push = useCallback(
    (kind: ToastKind, message: string, options: ToastOptions = {}) => {
      const id = crypto.randomUUID()
      const duration = options.duration ?? DEFAULT_DURATION[kind]
      const title = options.title ?? DEFAULT_TITLE[kind]

      setToasts((current) => [...current.slice(-3), { id, kind, title, message, createdAt: Date.now(), duration }])

      if (options.log !== false) {
        setNotifications((current) =>
          [
            { id, kind, title, message, at: Date.now(), read: false },
            ...current,
          ].slice(0, 20),
        )
      }

      if (options.sound !== false) {
        if (kind === "success") play("success")
        else if (kind === "error") play("error")
        else play("notify")
      }

      const timer = window.setTimeout(() => dismiss(id), duration)
      timers.current.set(id, timer)
      return id
    },
    [dismiss, play],
  )

  useEffect(() => {
    const pending = timers.current
    return () => {
      for (const timer of pending.values()) window.clearTimeout(timer)
      pending.clear()
    }
  }, [])

  const value = useMemo<ToastValue>(
    () => ({
      success: (message, options) => push("success", message, options),
      error: (message, options) => push("error", message, options),
      info: (message, options) => push("info", message, options),
      warning: (message, options) => push("warning", message, options),
      dismiss,
      notifications,
      unreadCount: notifications.filter((entry) => !entry.read).length,
      markAllRead: () =>
        setNotifications((current) => current.map((entry) => ({ ...entry, read: true }))),
      clearNotifications: () => setNotifications([]),
    }),
    [push, dismiss, notifications],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-3 top-3 z-[70] flex w-[min(24rem,calc(100vw-1.5rem))] flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((toast) => {
            const Icon = ICONS[toast.kind]
            return (
              <motion.div
                key={toast.id}
                layout
                initial={{ opacity: 0, y: -14, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: 24, scale: 0.98 }}
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
                className={`toast toast-${toast.kind}`}
                role={toast.kind === "error" ? "alert" : "status"}
                aria-live={toast.kind === "error" ? "assertive" : "polite"}
              >
                <span className={`toast-icon toast-icon-${toast.kind}`}>
                  <Icon size={16} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[12px] font-semibold text-white">{toast.title}</p>
                  <p className="mt-0.5 text-[11.5px] leading-[1.45] text-white/55">
                    {toast.message}
                  </p>
                </div>
                <button
                  type="button"
                  className="toast-close"
                  onClick={() => dismiss(toast.id)}
                  aria-label="Dismiss notification"
                >
                  <X size={13} />
                </button>
                <motion.span
                  className="toast-progress"
                  initial={{ scaleX: 1 }}
                  animate={{ scaleX: 0 }}
                  transition={{ duration: toast.duration / 1000, ease: "linear" }}
                />
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastValue {
  const value = useContext(ToastContext)
  if (!value) throw new Error("useToast must be used inside <ToastProvider>")
  return value
}
