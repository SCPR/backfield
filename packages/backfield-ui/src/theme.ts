/**
 * Light / Dark / System appearance shared by Agate, Stylebook and API Playground.
 *
 * The choice is stored in a cookie so it follows the user across the sibling apps:
 * localhost ports share cookies, and split hosts (`agate.{client}…`, `stylebook.{client}…`)
 * share it through their common parent domain. localStorage is a same-origin fallback.
 *
 * Each app's index.html carries a tiny inline copy of `applyStoredTheme` so the right
 * class is on <html> before first paint (no light flash in dark mode). Keep
 * THEME_STORAGE_KEY and the resolution rules in sync with that script.
 */
import { useCallback, useSyncExternalStore } from "react"

export type ThemePreference = "light" | "dark" | "system"
export type ResolvedTheme = "light" | "dark"

export const THEME_STORAGE_KEY = "backfield_theme"
export const THEME_PREFERENCES: readonly ThemePreference[] = ["light", "dark", "system"]

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365
const UI_HOST_LABELS = new Set(["agate", "stylebook", "playground"])
const THEME_CHANGE_EVENT = "backfield-theme-change"

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === "light" || value === "dark" || value === "system"
}

/**
 * Cookie domain shared by the sibling UI hosts, or null for host-only cookies.
 * `agate.cpm.backfield.news` → `cpm.backfield.news`; localhost / IPs / custom
 * single-app hosts → null (host-only; localhost already shares across ports).
 */
export function themeCookieDomain(hostname: string): string | null {
  const labels = hostname.toLowerCase().split(".")
  if (labels.length < 3) return null
  if (!UI_HOST_LABELS.has(labels[0])) return null
  return labels.slice(1).join(".")
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  for (const part of document.cookie.split(";")) {
    const [rawKey, ...rest] = part.trim().split("=")
    if (rawKey === name) return decodeURIComponent(rest.join("="))
  }
  return null
}

export function readThemePreference(): ThemePreference {
  const fromCookie = readCookie(THEME_STORAGE_KEY)
  if (isThemePreference(fromCookie)) return fromCookie
  try {
    const fromStorage = window.localStorage.getItem(THEME_STORAGE_KEY)
    if (isThemePreference(fromStorage)) return fromStorage
  } catch {
    // Storage can be unavailable (private mode, blocked site data).
  }
  return "system"
}

function writeThemePreference(preference: ThemePreference): void {
  const domain = themeCookieDomain(window.location.hostname)
  const secure = window.location.protocol === "https:" ? "; Secure" : ""
  const domainAttr = domain ? `; Domain=${domain}` : ""
  document.cookie =
    `${THEME_STORAGE_KEY}=${encodeURIComponent(preference)}; Path=/; Max-Age=${ONE_YEAR_SECONDS}` +
    `; SameSite=Lax${domainAttr}${secure}`
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference)
  } catch {
    // Cookie is the source of truth; storage is best-effort.
  }
}

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)").matches
    : false
}

export function resolveTheme(preference: ThemePreference, prefersDark: boolean): ResolvedTheme {
  if (preference === "system") return prefersDark ? "dark" : "light"
  return preference
}

/** Put the resolved theme on <html> (`dark` class for Tailwind, plus `color-scheme`). */
export function applyTheme(preference: ThemePreference = readThemePreference()): ResolvedTheme {
  const resolved = resolveTheme(preference, systemPrefersDark())
  const root = document.documentElement
  root.classList.toggle("dark", resolved === "dark")
  root.style.colorScheme = resolved
  return resolved
}

export function setThemePreference(preference: ThemePreference): void {
  writeThemePreference(preference)
  applyTheme(preference)
  window.dispatchEvent(new Event(THEME_CHANGE_EVENT))
}

/**
 * Call once at app startup: applies the stored theme, follows OS changes while the
 * preference is System, and re-reads the shared cookie when the tab regains focus (a
 * sibling app may have changed it). Returns a cleanup function.
 */
export function startThemeSync(): () => void {
  applyTheme()
  const reapply = () => applyTheme()
  const query =
    typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: dark)") : null
  query?.addEventListener("change", reapply)
  window.addEventListener("focus", reapply)
  return () => {
    query?.removeEventListener("change", reapply)
    window.removeEventListener("focus", reapply)
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(THEME_CHANGE_EVENT, onChange)
  // Another sibling app (or tab) may change the cookie; re-read when this tab regains focus.
  window.addEventListener("focus", onChange)
  return () => {
    window.removeEventListener(THEME_CHANGE_EVENT, onChange)
    window.removeEventListener("focus", onChange)
  }
}

/** Current preference plus a setter (the <html> class itself is kept in sync by startThemeSync). */
export function useThemePreference(): [ThemePreference, (preference: ThemePreference) => void] {
  const preference = useSyncExternalStore(subscribe, readThemePreference, () => "system" as const)
  const update = useCallback((next: ThemePreference) => setThemePreference(next), [])
  return [preference, update]
}
