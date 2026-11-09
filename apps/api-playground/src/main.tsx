import React from "react"
import ReactDOM from "react-dom/client"

import { startThemeSync } from "@backfield/ui/theme"
import App from "./App"
import "./styles.css"
// After styles.css: dark-mode equivalents for hard-coded palette classes.
import "@backfield/ui/theme-dark.css"

startThemeSync()

const root = document.getElementById("root")

if (!root) {
  throw new Error("Playground root element is missing")
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
