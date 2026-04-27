import './theme.css'
import './mobile.css'
import React from 'react'
import ReactDOM from 'react-dom/client'
import CerebroHUD from './CerebroHUD.jsx'

function App() {
  return <CerebroHUD />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
