import React from 'react'
import ReactDOM from 'react-dom/client'
import { App } from './App'
import './index.css'
import { installE2EHooks } from './e2e-hooks'

if (import.meta.env.VITE_E2E_HOOKS === '1') installE2EHooks();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)