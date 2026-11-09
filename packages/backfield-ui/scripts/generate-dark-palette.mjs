#!/usr/bin/env node
/**
 * Generate src/theme-dark.css: dark-mode equivalents for hard-coded Tailwind palette
 * classes (bg-white, text-gray-600, bg-amber-50, border-red-200, …) used across Agate,
 * Stylebook and API Playground, so those apps read correctly with the `dark` class on
 * <html> without editing every component.
 *
 * Rules are wrapped in :where(.dark) so they carry the same specificity as the utility
 * they remap. They win only because the stylesheet is imported after each app's Tailwind
 * CSS; any explicit `dark:` variant in a component (specificity 0,2,0) still takes
 * precedence.
 *
 * Usage (needs an app's tailwindcss for the palette):
 *   node scripts/generate-dark-palette.mjs ../../apps/agate-ui/node_modules/tailwindcss/colors.js
 */
import { writeFileSync } from "node:fs"
import { createRequire } from "node:module"
import path from "node:path"
import { fileURLToPath } from "node:url"

const here = path.dirname(fileURLToPath(import.meta.url))
const colorsPath = path.resolve(process.argv[2] ?? "")
if (!process.argv[2]) {
  console.error("usage: generate-dark-palette.mjs <path to tailwindcss/colors.js>")
  process.exit(2)
}
const colors = createRequire(import.meta.url)(colorsPath)

const NEUTRALS = ["gray", "slate", "zinc", "neutral", "stone"]
const HUES = [
  "red", "orange", "amber", "yellow", "lime", "green", "emerald", "teal", "cyan", "sky",
  "blue", "indigo", "violet", "purple", "fuchsia", "pink", "rose",
]

const token = (name, alpha) => (alpha == null ? `hsl(var(--${name}))` : `hsl(var(--${name}) / ${alpha})`)

function hexWithAlpha(hex, alpha) {
  const n = Number.parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return alpha == null ? `rgb(${r} ${g} ${b})` : `rgb(${r} ${g} ${b} / ${alpha})`
}

/** [utility prefix, CSS property] */
const PROPS = {
  bg: "background-color",
  text: "color",
  border: "border-color",
  divide: "border-color",
  placeholder: "color",
}

/** Escape a utility name for a CSS class selector. */
const esc = (cls) => cls.replace(/[:/.[\]]/g, (c) => `\\${c}`)

function selectorsFor(utility, prefix) {
  const base = `:where(.dark) .${esc(utility)}`
  if (prefix === "divide") {
    return [`${base} > :not([hidden]) ~ :not([hidden])`]
  }
  if (prefix === "placeholder") {
    return [`${base}::placeholder`]
  }
  const sels = [base]
  if (prefix === "bg" || prefix === "text" || prefix === "border") {
    sels.push(`:where(.dark) .${esc(`hover:${utility}`)}:hover`)
  }
  return sels
}

const rules = []
function rule(prefix, name, value) {
  const utility = `${prefix}-${name}`
  for (const sel of selectorsFor(utility, prefix)) {
    rules.push(`${sel} { ${PROPS[prefix]}: ${value}; }`)
  }
}

// Surfaces and text on the neutral palettes map onto the theme tokens.
rule("bg", "white", token("card"))
rule("text", "black", token("foreground"))
rule("border", "white", token("border"))
for (const n of NEUTRALS) {
  rule("bg", `${n}-50`, token("muted", 0.5))
  rule("bg", `${n}-100`, token("muted"))
  rule("bg", `${n}-200`, token("accent"))
  for (const s of ["950", "900", "800", "700"]) rule("text", `${n}-${s}`, token("foreground"))
  for (const s of ["600", "500", "400"]) rule("text", `${n}-${s}`, token("muted-foreground"))
  for (const s of ["100", "200", "300"]) {
    rule("border", `${n}-${s}`, token("border"))
    rule("divide", `${n}-${s}`, token("border"))
  }
  rule("placeholder", `${n}-400`, token("muted-foreground"))
  rule("placeholder", `${n}-500`, token("muted-foreground"))
}

// Tinted badges, callouts and pills: deep translucent fills, light text, muted borders.
for (const h of HUES) {
  const p = colors[h]
  if (!p) continue
  rule("bg", `${h}-50`, hexWithAlpha(p["950"], 0.4))
  rule("bg", `${h}-100`, hexWithAlpha(p["900"], 0.4))
  rule("bg", `${h}-200`, hexWithAlpha(p["800"], 0.5))
  rule("text", `${h}-950`, p["100"])
  rule("text", `${h}-900`, p["200"])
  rule("text", `${h}-800`, p["200"])
  rule("text", `${h}-700`, p["300"])
  rule("text", `${h}-600`, p["400"])
  rule("border", `${h}-100`, p["900"])
  rule("border", `${h}-200`, p["800"])
  rule("border", `${h}-300`, p["700"])
}

// Opacity-suffixed light tints (`bg-amber-200/90` mention highlights, `bg-amber-50/80` callouts,
// `text-amber-950/90`): match any `/NN` with an attribute selector, same 0,1,0 specificity.
// Mid and dark shades with opacity (`bg-amber-500/40`) already read on dark and are left alone.
const attr = (fragment) => `:where(.dark) [class*="${fragment}"]`
for (const h of HUES) {
  const p = colors[h]
  if (!p) continue
  for (const [s, base, alpha] of [["50", "950", 0.4], ["100", "900", 0.4], ["200", "800", 0.55], ["300", "700", 0.55]]) {
    rules.push(`${attr(`bg-${h}-${s}/`)} { background-color: ${hexWithAlpha(p[base], alpha)}; }`)
  }
  for (const [s, light] of [["950", "100"], ["900", "200"], ["800", "200"], ["700", "300"]]) {
    rules.push(`${attr(`text-${h}-${s}/`)} { color: ${p[light]}; }`)
  }
  for (const [s, dark] of [["100", "900"], ["200", "800"], ["300", "700"]]) {
    rules.push(`${attr(`border-${h}-${s}/`)} { border-color: ${p[dark]}; }`)
  }
}

const header = `/* Generated by scripts/generate-dark-palette.mjs. Do not edit by hand. */
/* Dark-mode equivalents for hard-coded Tailwind palette classes; see the script for the rules. */
`
const out = path.join(here, "..", "src", "theme-dark.css")
writeFileSync(out, `${header}${rules.join("\n")}\n`)
console.log(`wrote ${rules.length} rules to ${path.relative(process.cwd(), out)}`)
