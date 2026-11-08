import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { startThemeSync } from '@backfield/ui/theme'
import App from './App.tsx'
import './index.css'
// After index.css: dark-mode equivalents for hard-coded palette classes.
import '@backfield/ui/theme-dark.css'

startThemeSync()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)

