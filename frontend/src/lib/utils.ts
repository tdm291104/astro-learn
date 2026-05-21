import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const RELATIVE_TIME_UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 60 * 60 * 24 * 365],
  ["month", 60 * 60 * 24 * 30],
  ["day", 60 * 60 * 24],
  ["hour", 60 * 60],
  ["minute", 60],
  ["second", 1],
]

export function formatRelativeTime(iso: string): string {
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return ""
  const diffSec = Math.round((ts - Date.now()) / 1000)
  if (Math.abs(diffSec) < 5) return "just now"
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" })
  for (const [unit, secInUnit] of RELATIVE_TIME_UNITS) {
    if (Math.abs(diffSec) >= secInUnit || unit === "second") {
      return rtf.format(Math.round(diffSec / secInUnit), unit)
    }
  }
  return ""
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ["KB", "MB", "GB", "TB"]
  let size = bytes / 1024
  let unitIdx = 0
  while (size >= 1024 && unitIdx < units.length - 1) {
    size /= 1024
    unitIdx++
  }
  return `${size.toFixed(1)} ${units[unitIdx]}`
}
