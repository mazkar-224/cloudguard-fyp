import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Toaster } from 'sonner'
import Layout from './components/Layout'
import DashboardPage from './pages/DashboardPage'
import AlertsPage from './pages/AlertsPage'
import RecommendationsPage from './pages/RecommendationsPage'
import SettingsPage from './pages/SettingsPage'

/*
  Toaster is mounted here (outside the route tree) so toasts appear on
  every page. richColors gives success toasts a green background and
  error toasts a red one — no custom styling needed.
*/
function App() {
  return (
    <BrowserRouter>
      <Toaster position="bottom-right" richColors closeButton />
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="alerts"   element={<AlertsPage />} />
          <Route path="recommendations" element={<RecommendationsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
