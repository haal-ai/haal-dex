import { useState } from 'react'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ThemeProvider, useTheme } from '../ThemeProvider'

const STORAGE_KEY = 'intent-theme'

function mockMatchMedia(prefersDark: boolean) {
  const mql = {
    matches: prefersDark,
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    ...mql,
    matches: query === '(prefers-color-scheme: dark)' ? prefersDark : false,
    media: query,
  }))
}

/** Helper component that exposes theme context for testing */
function ThemeConsumer() {
  const { theme, toggleTheme, setTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button data-testid="toggle" onClick={toggleTheme}>Toggle</button>
      <button data-testid="set-dark" onClick={() => setTheme('dark')}>Dark</button>
      <button data-testid="set-light" onClick={() => setTheme('light')}>Light</button>
    </div>
  )
}

function renderWithProvider() {
  return render(
    <ThemeProvider>
      <ThemeConsumer />
    </ThemeProvider>
  )
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
    mockMatchMedia(false) // default: OS prefers light
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  describe('OS theme detection as default', () => {
    it('defaults to dark when OS prefers dark', () => {
      mockMatchMedia(true)
      renderWithProvider()
      expect(screen.getByTestId('theme').textContent).toBe('dark')
      expect(document.documentElement.classList.contains('dark')).toBe(true)
    })

    it('defaults to light when OS prefers light', () => {
      mockMatchMedia(false)
      renderWithProvider()
      expect(screen.getByTestId('theme').textContent).toBe('light')
      expect(document.documentElement.classList.contains('dark')).toBe(false)
    })
  })

  describe('manual toggle switches between dark and light', () => {
    it('toggles from light to dark', async () => {
      mockMatchMedia(false)
      renderWithProvider()
      expect(screen.getByTestId('theme').textContent).toBe('light')

      const user = userEvent.setup()
      await user.click(screen.getByTestId('toggle'))

      expect(screen.getByTestId('theme').textContent).toBe('dark')
      expect(document.documentElement.classList.contains('dark')).toBe(true)
    })

    it('toggles from dark to light', async () => {
      mockMatchMedia(true)
      renderWithProvider()
      expect(screen.getByTestId('theme').textContent).toBe('dark')

      const user = userEvent.setup()
      await user.click(screen.getByTestId('toggle'))

      expect(screen.getByTestId('theme').textContent).toBe('light')
      expect(document.documentElement.classList.contains('dark')).toBe(false)
    })

    it('setTheme explicitly sets the theme', async () => {
      mockMatchMedia(false)
      renderWithProvider()
      expect(screen.getByTestId('theme').textContent).toBe('light')

      const user = userEvent.setup()
      await user.click(screen.getByTestId('set-dark'))
      expect(screen.getByTestId('theme').textContent).toBe('dark')

      await user.click(screen.getByTestId('set-light'))
      expect(screen.getByTestId('theme').textContent).toBe('light')
    })
  })

  describe('theme persists in localStorage', () => {
    it('saves theme to localStorage on toggle', async () => {
      mockMatchMedia(false)
      renderWithProvider()

      const user = userEvent.setup()
      await user.click(screen.getByTestId('toggle'))

      expect(localStorage.getItem(STORAGE_KEY)).toBe('dark')
    })

    it('restores theme from localStorage on mount', () => {
      localStorage.setItem(STORAGE_KEY, 'dark')
      renderWithProvider()
      expect(screen.getByTestId('theme').textContent).toBe('dark')
      expect(document.documentElement.classList.contains('dark')).toBe(true)
    })

    it('localStorage preference overrides OS preference', () => {
      // OS prefers light, but localStorage says dark
      mockMatchMedia(false)
      localStorage.setItem(STORAGE_KEY, 'dark')

      renderWithProvider()
      expect(screen.getByTestId('theme').textContent).toBe('dark')
    })
  })

  describe('session state is not affected by theme changes', () => {
    it('preserves child component state across theme toggles', async () => {
      function StatefulChild() {
        const [count, setCount] = useState(0)
        const { toggleTheme, theme } = useTheme()
        return (
          <div>
            <span data-testid="count">{count}</span>
            <span data-testid="child-theme">{theme}</span>
            <button data-testid="increment" onClick={() => setCount(c => c + 1)}>+</button>
            <button data-testid="child-toggle" onClick={toggleTheme}>Toggle</button>
          </div>
        )
      }

      mockMatchMedia(false)

      render(
        <ThemeProvider>
          <StatefulChild />
        </ThemeProvider>
      )

      const user = userEvent.setup()

      // Build up some session state
      await user.click(screen.getByTestId('increment'))
      await user.click(screen.getByTestId('increment'))
      await user.click(screen.getByTestId('increment'))
      expect(screen.getByTestId('count').textContent).toBe('3')

      // Toggle theme
      await user.click(screen.getByTestId('child-toggle'))
      expect(screen.getByTestId('child-theme').textContent).toBe('dark')

      // Session state preserved
      expect(screen.getByTestId('count').textContent).toBe('3')

      // Toggle back
      await user.click(screen.getByTestId('child-toggle'))
      expect(screen.getByTestId('child-theme').textContent).toBe('light')
      expect(screen.getByTestId('count').textContent).toBe('3')
    })
  })

  describe('useTheme hook', () => {
    it('throws when used outside ThemeProvider', () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

      expect(() => {
        render(<ThemeConsumer />)
      }).toThrow('useTheme must be used within a ThemeProvider')

      spy.mockRestore()
    })
  })
})
