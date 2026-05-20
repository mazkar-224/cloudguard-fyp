import { useState, useEffect } from 'react'

/*
  useDarkMode — reads/writes dark mode preference to localStorage and
  keeps the `dark` class on <html> in sync.

  Why toggle a class on <html> instead of passing a prop down?
    Tailwind's dark: variant is configured to activate when any ancestor
    has the `dark` class. Setting it on <html> covers the entire page
    in one place — no prop drilling needed.

  FOUC (flash of unstyled content):
    On a cold page load, React hasn't run yet when the browser first paints.
    To prevent a visible light→dark flash, index.html contains an inline
    <script> that reads localStorage synchronously and applies the class
    before the first paint. This hook then syncs with that initial value.
*/
export function useDarkMode() {
  const [dark, setDark] = useState(() => {
    if (typeof localStorage === 'undefined') return false
    const stored = localStorage.getItem('theme')
    // Explicit stored choice takes priority.
    // Fall back to OS preference so first-time visitors with dark OS get dark mode.
    if (stored) return stored === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    const root = document.documentElement
    if (dark) {
      root.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      root.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }, [dark])

  return [dark, setDark]
}
