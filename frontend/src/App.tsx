import { AnimatePresence, motion } from "framer-motion"
import { ArrowRight, ShieldCheck } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { AppShell } from "./components/AppShell"
import { Brand } from "./components/Brand"
import { CookieConsent } from "./components/CookieConsent"
import { Guidelines } from "./components/Guidelines"
import { History } from "./components/History"
import { Login } from "./components/Login"
import { Review } from "./components/Review"
import { Security } from "./components/Security"
import { useAuth } from "./lib/auth"
import { Link, useRouter } from "./lib/router"

const PUBLIC_PATHS = new Set(["/app/guide", "/app/security"])
const PROTECTED_PATHS = new Set(["/app/review", "/app/history"])

/**
 * How long the branded splash stays up at minimum.
 *
 * Auth resolves in a few milliseconds on a warm cache, which is shorter than
 * one frame of the intro animation, so an unconditional "hide as soon as we
 * know" would flash the video for a blink and never show it at all. Set this
 * to 0 to drop the splash the instant the session is known.
 */
const SPLASH_MIN_MS = 1600

const BRAND_URL = `${import.meta.env.BASE_URL}brand/leaselens-mark.png`
const SPLASH_VIDEO_URL = `${import.meta.env.BASE_URL}brand/loading.mp4`

/** A decorative 7.6s intro loop is exactly what reduced-motion users asked us not to play. */
function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

export default function App() {
  const { status } = useAuth()
  const { path, navigate } = useRouter()
  const [splashDone, setSplashDone] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => setSplashDone(true), SPLASH_MIN_MS)
    return () => window.clearTimeout(timer)
  }, [])

  useEffect(() => {
    if (status === "booting") return

    if (path === "/") {
      navigate(status === "authenticated" ? "/app/review" : "/login", { replace: true })
      return
    }
    if (path === "/login" && status === "authenticated") {
      navigate("/app/review", { replace: true })
      return
    }
    if (PROTECTED_PATHS.has(path) && status === "anonymous") {
      navigate("/login", { replace: true })
      return
    }
    if (
      !PUBLIC_PATHS.has(path) &&
      !PROTECTED_PATHS.has(path) &&
      path !== "/login"
    ) {
      navigate(status === "authenticated" ? "/app/review" : "/login", { replace: true })
    }
  }, [status, path, navigate])

  if (status === "booting" || !splashDone) {
    return <Splash />
  }

  if (path === "/login" || (status === "anonymous" && PROTECTED_PATHS.has(path))) {
    return (
      <>
        <Login onSuccess={() => navigate("/app/review", { replace: true })} />
        <CookieConsent />
      </>
    )
  }

  if (PUBLIC_PATHS.has(path)) {
    const page = path === "/app/guide" ? <Guidelines /> : <Security />
    return (
      <>
        {status === "authenticated" ? (
          <AppShell>{page}</AppShell>
        ) : (
          <PublicShell>{page}</PublicShell>
        )}
        <CookieConsent />
      </>
    )
  }

  if (status === "authenticated") {
    return (
      <>
        <AppShell>
          <AnimatePresence mode="wait">
            <motion.div
              key={path}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18 }}
            >
              {path === "/app/history" ? <History /> : <Review />}
            </motion.div>
          </AnimatePresence>
        </AppShell>
        <CookieConsent />
      </>
    )
  }

  return (
    <>
      <Login onSuccess={() => navigate("/app/review", { replace: true })} />
      <CookieConsent />
    </>
  )
}

/**
 * Boot splash.
 *
 * The intro clip is muted and inline so every browser is allowed to autoplay
 * it, loops while the session is resolved, and falls back to the still mark
 * when the visitor asked for reduced motion or the codec is unsupported
 * (`onError` swaps to the poster rather than leaving a black tile).
 */
function Splash() {
  const [videoFailed, setVideoFailed] = useState(false)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const showVideo = !prefersReducedMotion() && !videoFailed

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    // The attribute alone is not always enough on the first frame, and a refused
    // play() must not leave a frozen tile: the poster stays in that case.
    video.muted = true
    void video.play().catch(() => undefined)
  }, [showVideo])

  return (
    <div className="grid min-h-screen place-items-center bg-ink">
      <motion.div
        className="text-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
      >
        <div className="splash-tile mx-auto">
          {showVideo ? (
            <video
              ref={videoRef}
              autoPlay
              muted
              loop
              playsInline
              preload="auto"
              poster={BRAND_URL}
              aria-hidden="true"
              disablePictureInPicture
              onError={() => setVideoFailed(true)}
            >
              <source src={SPLASH_VIDEO_URL} type="video/mp4" />
            </video>
          ) : (
            <img src={BRAND_URL} alt="LeaseLens" />
          )}
        </div>
        <p className="mono-label mt-6 text-white/30">Preparing your workspace</p>
      </motion.div>
    </div>
  )
}

/** Minimal chrome for the two documents that are readable before signing in. */
function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-ink">
      <header className="sticky top-0 z-40 border-b border-white/8 bg-ink/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6">
          <Brand asLink={false} />
          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-1.5 text-[11px] text-white/35 sm:flex">
              <ShieldCheck size={12} className="text-mint" /> No account needed to read this
            </span>
            <Link to="/login" className="ghost-button">
              Sign in <ArrowRight size={13} />
            </Link>
          </div>
        </div>
      </header>
      <main className="pb-16">{children}</main>
    </div>
  )
}
