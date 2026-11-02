import { Link } from "../lib/router"

const MARK = `${import.meta.env.BASE_URL}brand/leaselens-mark.png`

/**
 * The wordmark sits next to the aperture mark. The mark is a real raster asset
 * (not an inline icon) so the favicon, the header and social previews all show
 * the same thing.
 */
export function Brand({
  compact = false,
  size = "md",
  asLink = false,
}: {
  compact?: boolean
  size?: "sm" | "md" | "lg"
  asLink?: boolean
}) {
  const box = size === "lg" ? "size-12" : size === "sm" ? "size-7" : "size-9"
  const radius = size === "lg" ? "rounded-2xl" : "rounded-xl"
  const text = size === "lg" ? "text-lg" : size === "sm" ? "text-[13px]" : "text-[15px]"

  const inner = (
    <span className="flex items-center gap-2.5" aria-label="LeaseLens">
      <span className={`brand-mark ${box} ${radius}`}>
        <img src={MARK} alt="" aria-hidden="true" draggable={false} />
      </span>
      {!compact && (
        <span className={`${text} font-semibold tracking-[-0.03em] text-white`}>
          Lease<span className="text-white/45">Lens</span>
        </span>
      )}
    </span>
  )

  if (!asLink) return inner
  return (
    <Link to="/app/review" className="inline-flex items-center rounded-lg">
      {inner}
    </Link>
  )
}
