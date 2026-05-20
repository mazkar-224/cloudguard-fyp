import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'

function Layout() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 min-h-[calc(100vh-3.5rem)] overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default Layout
