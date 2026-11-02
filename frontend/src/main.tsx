import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App"
import { AuthProvider } from "./lib/auth"
import { ConsentProvider } from "./lib/consent"
import { ReviewProvider } from "./lib/review"
import { RouterProvider } from "./lib/router"
import { SoundProvider } from "./lib/sound"
import { ToastProvider } from "./lib/toast"
import "./index.css"

/**
 * Provider order matters:
 *
 *  ConsentProvider   outermost stateful layer - sound persistence reads it,
 *                    so it has to be mounted first.
 *  SoundProvider     owns the single AudioContext; toasts call into it.
 *  ToastProvider     renders the notification bars, needs sound.
 *  AuthProvider      needs nothing above it, but every page below needs it.
 *  ReviewProvider    holds the report currently on screen, shared by the
 *                    review workspace and the history restore path.
 */
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider>
      <ConsentProvider>
        <SoundProvider>
          <ToastProvider>
            <AuthProvider>
              <ReviewProvider>
                <App />
              </ReviewProvider>
            </AuthProvider>
          </ToastProvider>
        </SoundProvider>
      </ConsentProvider>
    </RouterProvider>
  </StrictMode>,
)
