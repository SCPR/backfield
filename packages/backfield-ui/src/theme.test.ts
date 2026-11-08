import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  applyTheme,
  readThemePreference,
  resolveTheme,
  setThemePreference,
  THEME_STORAGE_KEY,
  themeCookieDomain,
} from "./theme"

function mockSystemDark(dark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: dark && query.includes("dark"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
}

function clearThemeCookie() {
  document.cookie = `${THEME_STORAGE_KEY}=; Path=/; Max-Age=0`
}

describe("themeCookieDomain", () => {
  it("shares the cookie across sibling split hosts", () => {
    expect(themeCookieDomain("agate.cpm.backfield.news")).toBe("cpm.backfield.news")
    expect(themeCookieDomain("stylebook.stg.cpm.backfield.news")).toBe("stg.cpm.backfield.news")
    expect(themeCookieDomain("playground.cpm.backfield.news")).toBe("cpm.backfield.news")
  })

  it("stays host-only for localhost, IPs and custom single-app hosts", () => {
    expect(themeCookieDomain("localhost")).toBeNull()
    expect(themeCookieDomain("127.0.0.1")).toBeNull()
    expect(themeCookieDomain("news.example.org")).toBeNull()
  })
})

describe("resolveTheme", () => {
  it("follows the OS only for system", () => {
    expect(resolveTheme("system", true)).toBe("dark")
    expect(resolveTheme("system", false)).toBe("light")
    expect(resolveTheme("light", true)).toBe("light")
    expect(resolveTheme("dark", false)).toBe("dark")
  })
})

describe("theme preference", () => {
  beforeEach(() => {
    clearThemeCookie()
    window.localStorage.clear()
    document.documentElement.classList.remove("dark")
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("defaults to system", () => {
    expect(readThemePreference()).toBe("system")
  })

  it("persists the choice and applies the dark class", () => {
    mockSystemDark(false)
    setThemePreference("dark")
    expect(readThemePreference()).toBe("dark")
    expect(document.cookie).toContain(`${THEME_STORAGE_KEY}=dark`)
    expect(document.documentElement.classList.contains("dark")).toBe(true)
    expect(document.documentElement.style.colorScheme).toBe("dark")

    setThemePreference("light")
    expect(document.documentElement.classList.contains("dark")).toBe(false)
  })

  it("applies the OS preference when set to system", () => {
    mockSystemDark(true)
    expect(applyTheme("system")).toBe("dark")
    expect(document.documentElement.classList.contains("dark")).toBe(true)
  })

  it("ignores an invalid stored value", () => {
    document.cookie = `${THEME_STORAGE_KEY}=purple; Path=/`
    expect(readThemePreference()).toBe("system")
  })
})
