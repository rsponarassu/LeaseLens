import { motion } from "framer-motion"
import { FileText, LockKeyhole, ScanLine, UploadCloud } from "lucide-react"
import { useRef, useState } from "react"
import type { DragEvent } from "react"
import { formatBytes } from "../lib/format"

const DEFAULT_MAX_MB = 15

export function UploadZone({
  onFile,
  onReject,
  disabled = false,
  maxMb = DEFAULT_MAX_MB,
}: {
  onFile: (file: File) => void
  onReject?: (message: string) => void
  disabled?: boolean
  maxMb?: number
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const handle = (file?: File) => {
    if (!file) return
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")
    if (!isPdf) {
      onReject?.(`“${file.name}” is not a PDF. Export your agreement as PDF and try again.`)
      return
    }
    if (file.size > maxMb * 1024 * 1024) {
      onReject?.(
        `That file is ${formatBytes(file.size)}. The limit is ${maxMb} MB — compress it or split the scan.`,
      )
      return
    }
    if (file.size === 0) {
      onReject?.("That file is empty.")
      return
    }
    onFile(file)
  }

  const drop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    if (disabled) return
    handle(event.dataTransfer.files[0])
  }

  return (
    <motion.div
      className={`group relative overflow-hidden rounded-[28px] border p-2 transition-colors ${
        dragging ? "border-cobalt bg-cobalt/10" : "border-white/12 bg-white/[0.035]"
      } ${disabled ? "pointer-events-none opacity-60" : ""}`}
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
      whileHover={disabled ? undefined : { y: -3 }}
    >
      <button
        type="button"
        className="relative flex min-h-64 w-full flex-col items-center justify-center overflow-hidden rounded-[22px] border border-dashed border-white/15 bg-black/15 px-5 text-center focus-visible:outline focus-visible:outline-2 focus-visible:outline-cobalt"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
      >
        <div className="upload-rings absolute left-1/2 top-1/2 size-72 -translate-x-1/2 -translate-y-1/2 rounded-full" />
        <motion.span
          className="relative mb-5 grid size-16 place-items-center rounded-2xl border border-white/12 bg-white/[0.07] text-cobalt shadow-xl shadow-black/25"
          whileHover={{ rotate: -4, scale: 1.06 }}
        >
          <UploadCloud size={25} />
        </motion.span>
        <span className="relative text-xl font-semibold tracking-[-0.03em] text-white">
          Drop your rental agreement
        </span>
        <span className="relative mt-2 text-sm text-white/38">
          or click to browse · PDF up to {maxMb} MB
        </span>
        <span className="relative mt-6 rounded-full bg-white/[0.06] px-4 py-2 text-xs font-medium text-white/55">
          Choose a PDF
        </span>
      </button>
      <input
        ref={inputRef}
        className="sr-only"
        type="file"
        accept="application/pdf,.pdf"
        onChange={(event) => {
          handle(event.target.files?.[0])
          event.target.value = ""
        }}
      />
      <div className="grid grid-cols-3 gap-2 px-3 py-4 text-[10px] uppercase tracking-[0.12em] text-white/30 sm:text-xs">
        <span className="flex items-center justify-center gap-2">
          <LockKeyhole size={13} /> Never stored
        </span>
        <span className="flex items-center justify-center gap-2">
          <ScanLine size={13} /> Clause scan
        </span>
        <span className="flex items-center justify-center gap-2">
          <FileText size={13} /> PDF only
        </span>
      </div>
    </motion.div>
  )
}
