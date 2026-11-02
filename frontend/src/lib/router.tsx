/**
 * A 60-line hash router.
 *
 * Hash routing is a deliberate choice: the same build is served by Vite in
 * development and by FastAPI's StaticFiles in production, and neither needs
 * rewrite rules or a catch-all route to make `/app/history` resolvable.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"

export type RoutePath =
  | "/"
  | "/login"
  | "/app/review"
  | "/app/history"
  | "/app/guide"
  | "/app/security"

interface RouterValue {
  path: RoutePath
  navigate: (to: RoutePath | string, options?: { replace?: boolean }) => void
}

const RouterContext = createContext<RouterValue | null>(null)

function readHash(): RoutePath {
  const raw = window.location.hash.replace(/^#/, "")
  const path = raw.split("?")[0] || "/"
  if (path.length > 1 && path.endsWith("/")) return path.slice(0, -1) as RoutePath
  return path as RoutePath
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState<RoutePath>(() => readHash())

  useEffect(() => {
    const onChange = () => setPath(readHash())
    window.addEventListener("hashchange", onChange)
    return () => window.removeEventListener("hashchange", onChange)
  }, [])

  const navigate = useCallback((to: string, options?: { replace?: boolean }) => {
    const target = `#${to.startsWith("/") ? to : `/${to}`}`
    if (window.location.hash === target) return
    if (options?.replace) {
      const url = `${window.location.pathname}${window.location.search}${target}`
      window.history.replaceState(null, "", url)
      setPath(readHash())
    } else {
      window.location.hash = target
    }
    window.scrollTo({ top: 0, behavior: "auto" })
  }, [])

  const value = useMemo(() => ({ path, navigate }), [path, navigate])
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter(): RouterValue {
  const value = useContext(RouterContext)
  if (!value) throw new Error("useRouter must be used inside <RouterProvider>")
  return value
}

export function Link({
  to,
  className,
  children,
  onNavigate,
}: {
  to: RoutePath | string
  className?: string
  children: ReactNode
  onNavigate?: () => void
}) {
  const { navigate } = useRouter()
  return (
    <a
      href={`#${to}`}
      className={className}
      onClick={(event) => {
        event.preventDefault()
        onNavigate?.()
        navigate(to)
      }}
    >
      {children}
    </a>
  )
}
