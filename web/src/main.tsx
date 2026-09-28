import React from 'react'
import ReactDOM from 'react-dom/client'
import { setDefaultClient } from '@chanx-js/client/react'
import App from './App.tsx'
import './index.css'

// Same origin, so Vite's dev proxy forwards /ws to the backend and cookies ride
// along. Channel addresses from the generated descriptors resolve against this.
setDefaultClient({
  baseUrl: `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`,
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
