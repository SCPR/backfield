// Applies the saved Light/Dark/System appearance before first paint (no light flash in
// dark mode). Loaded synchronously from index.html as a same-origin file so it also works
// under API Playground's `script-src 'self'` CSP. Keep in sync with
// packages/backfield-ui/src/theme.ts (THEME_STORAGE_KEY and resolution rules) and the
// copies in the other apps' public/ folders.
;(function () {
  try {
    var key = "backfield_theme"
    var pref = null
    var match = document.cookie.match(/(?:^|;\s*)backfield_theme=([^;]*)/)
    if (match) pref = decodeURIComponent(match[1])
    if (pref !== "light" && pref !== "dark" && pref !== "system") {
      try {
        pref = window.localStorage.getItem(key)
      } catch (e) {
        pref = null
      }
    }
    var dark =
      pref === "dark" ||
      (pref !== "light" &&
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches)
    var root = document.documentElement
    if (dark) root.classList.add("dark")
    root.style.colorScheme = dark ? "dark" : "light"
  } catch (e) {
    // Never block page load over appearance.
  }
})()
