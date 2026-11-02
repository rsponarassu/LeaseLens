import { AnimatePresence, motion } from "framer-motion"
import {
  Bell,
  BookOpen,
  Check,
  CircleHelp,
  Clock3,
  Cookie,
  FileSearch,
  History as HistoryIcon,
  LogOut,
  Settings2,
  ShieldCheck,
  Volume2,
  VolumeX,
  X,
} from "lucide-react"
import { useEffect, useState } from "react"
import type { ReactNode } from "react"
import { Brand } from "./Brand"
import { useAuth } from "../lib/auth"
import { useConsent } from "../lib/consent"
import { formatRelative, initialsFrom } from "../lib/format"
import { Link, useRouter } from "../lib/router"
import { useSound } from "../lib/sound"
import { useToast } from "../lib/toast"

const NAV = [
  { to: "/app/review", label: "Review", icon: FileSearch },
  { to: "/app/history", label: "History", icon: HistoryIcon },
  { to: "/app/guide", label: "Guidelines", icon: BookOpen },
  { to: "/app/security", label: "Security", icon: ShieldCheck },
] as const

export function AppShell({ children }: { children: ReactNode }) {
  const { path, navigate } = useRouter()
  const { user, signOut, mode } = useAuth()
  const { enabled, toggle, play } = useSound()
  const { notifications, unreadCount, markAllRead, clearNotifications } = useToast()
  const { openPreferences } = useConsent()
  const toast = useToast()
  const [menuOpen, setMenuOpen] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)

  useEffect(() => {
    if (!menuOpen && !bellOpen) return
    const close = () => {
      setMenuOpen(false)
      setBellOpen(false)
    }
    window.addEventListener("hashchange", close)
    return () => window.removeEventListener("hashchange", close)
  }, [menuOpen, bellOpen])

  const closeAll = () => {
    setMenuOpen(false)
    setBellOpen(false)
  }

  const handleSignOut = async () => {
    closeAll()
    await signOut()
    toast.info("You are signed out. Your saved reviews stay in your account.", { title: "Signed out" })
    navigate("/login")
  }

  return (
    <div className="min-h-screen bg-ink">
      <header className="sticky top-0 z-40 border-b border-white/8 bg-ink/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-5">
            <Brand asLink />
            <span className="hidden h-5 w-px bg-white/10 md:block" />
            <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
              {NAV.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`nav-item ${path === item.to ? "active" : ""}`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-1">
            <button
              className="icon-button"
              onClick={() => {
                toggle()
                if (!enabled) play("tap")
              }}
              aria-label={enabled ? "Mute interface sounds" : "Enable interface sounds"}
              title={enabled ? "Sound on" : "Sound off"}
            >
              {enabled ? <Volume2 size={17} /> : <VolumeX size={17} />}
            </button>

            <div className="relative">
              <button
                className="icon-button"
                onClick={() => {
                  setBellOpen((value) => !value)
                  setMenuOpen(false)
                  if (!bellOpen) {
                    markAllRead()
                    play("tap")
                  }
                }}
                aria-label="Notifications"
                aria-expanded={bellOpen}
              >
                <Bell size={17} />
                {unreadCount > 0 && <span className="bell-dot">{unreadCount}</span>}
              </button>
              <AnimatePresence>
                {bellOpen && (
                  <>
                    <button
                      className="fixed inset-0 z-40 cursor-default"
                      aria-label="Close notifications"
                      onClick={closeAll}
                    />
                    <motion.div
                      className="absolute right-0 top-11 z-50 w-[min(22rem,calc(100vw-1.5rem))] overflow-hidden rounded-xl border border-white/10 bg-[#141518] shadow-2xl"
                      initial={{ opacity: 0, y: -6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -6 }}
                    >
                      <div className="flex items-center justify-between border-b border-white/8 px-3 py-2.5">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/45">
                          Activity
                        </p>
                        {notifications.length > 0 && (
                          <button
                            className="text-[11px] text-white/35 hover:text-white"
                            onClick={clearNotifications}
                          >
                            Clear
                          </button>
                        )}
                      </div>
                      <div className="max-h-80 overflow-y-auto scroll-thin">
                        {notifications.length === 0 ? (
                          <p className="px-4 py-8 text-center text-xs leading-5 text-white/30">
                            Nothing yet. Analyses, downloads and errors show up here.
                          </p>
                        ) : (
                          notifications.map((entry) => (
                            <div
                              key={entry.id}
                              className="flex gap-2.5 border-b border-white/5 px-3 py-2.5 last:border-0"
                            >
                              <span className={`entry-dot ${entry.kind}`} />
                              <div className="min-w-0">
                                <p className="truncate text-[11.5px] font-medium text-white/80">
                                  {entry.title}
                                </p>
                                <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-white/40">
                                  {entry.message}
                                </p>
                                <p className="mt-1 text-[10px] text-white/25">
                                  {formatRelative(new Date(entry.at).toISOString())}
                                </p>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </motion.div>
                  </>
                )}
              </AnimatePresence>
            </div>

            <Link to="/app/guide" className="icon-button hidden sm:grid" aria-label="Help and guidelines">
              <CircleHelp size={17} />
            </Link>

            <span className="mx-1.5 hidden h-5 w-px bg-white/10 sm:block" />

            <div className="relative">
              <button
                className="avatar-button"
                onClick={() => {
                  setMenuOpen((value) => !value)
                  setBellOpen(false)
                }}
                aria-label="Account menu"
                aria-expanded={menuOpen}
              >
                {initialsFrom(user?.name ?? user?.email ?? "")}
              </button>
              <AnimatePresence>
                {menuOpen && (
                  <>
                    <button
                      className="fixed inset-0 z-40 cursor-default"
                      aria-label="Close menu"
                      onClick={closeAll}
                    />
                    <motion.div
                      className="absolute right-0 top-11 z-50 w-60 overflow-hidden rounded-xl border border-white/10 bg-[#141518] p-1.5 shadow-2xl"
                      initial={{ opacity: 0, y: -6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -6 }}
                    >
                      <div className="px-2.5 py-2">
                        <p className="truncate text-xs font-semibold text-white">
                          {user?.name ?? "Your account"}
                        </p>
                        <p className="truncate text-[11px] text-white/40">{user?.email}</p>
                        <span className={`storage-pill mt-2 ${mode}`}>
                          {mode === "cloud" ? (
                            <>
                              <Check size={10} /> Cloud account
                            </>
                          ) : (
                            <>
                              <Clock3 size={10} /> This device only
                            </>
                          )}
                        </span>
                      </div>
                      <div className="my-1 h-px bg-white/8" />
                      <Link to="/app/history" className="menu-item" onNavigate={closeAll}>
                        <HistoryIcon size={14} /> Past reviews
                      </Link>
                      <Link to="/app/security" className="menu-item" onNavigate={closeAll}>
                        <ShieldCheck size={14} /> Privacy &amp; security
                      </Link>
                      <button
                        className="menu-item"
                        onClick={() => {
                          closeAll()
                          openPreferences()
                        }}
                      >
                        <Cookie size={14} /> Cookie preferences
                      </button>
                      <button
                        className="menu-item"
                        onClick={() => {
                          closeAll()
                          navigate("/app/guide")
                        }}
                      >
                        <Settings2 size={14} /> How LeaseLens works
                      </button>
                      <div className="my-1 h-px bg-white/8" />
                      <button className="menu-item" onClick={handleSignOut}>
                        <LogOut size={14} /> Sign out
                      </button>
                    </motion.div>
                  </>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </header>

      <main className="pb-20 md:pb-0">{children}</main>

      <footer className="hidden border-t border-white/8 px-6 py-6 md:block">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3 text-[11px] text-white/28">
          <p>
            LeaseLens provides legal information, not legal advice. Verify critical terms with an
            advocate.
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <Link to="/app/guide" className="hover:text-white">
              Guidelines
            </Link>
            <Link to="/app/security" className="hover:text-white">
              Security
            </Link>
            <button className="hover:text-white" onClick={openPreferences}>
              Cookies
            </button>
            <span className="font-mono text-[10px] text-white/20">v1.0.0</span>
          </div>
        </div>
      </footer>

      <nav className="mobile-tabs md:hidden" aria-label="Primary">
        {NAV.map((item) => {
          const Icon = item.icon
          const active = path === item.to
          return (
            <Link key={item.to} to={item.to} className={`mobile-tab ${active ? "active" : ""}`}>
              <Icon size={18} />
              <span>{item.label}</span>
            </Link>
          )
        })}
        <button className="mobile-tab" onClick={openPreferences} aria-label="Cookie preferences">
          <Cookie size={18} />
          <span>Cookies</span>
        </button>
        <button className="mobile-tab" onClick={handleSignOut} aria-label="Sign out">
          <X size={18} />
          <span>Exit</span>
        </button>
      </nav>
    </div>
  )
}
