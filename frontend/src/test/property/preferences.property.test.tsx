/**
 * Property 25: UI preference changes preserve session state
 * Validates: Requirements 15.3, 16.2
 *
 * Switching language or theme preserves all non-preference session state.
 */
import { useState } from 'react'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import * as fc from 'fast-check'
import { ThemeProvider, useTheme } from '../../providers/ThemeProvider'
import { I18nProvider, useLanguage, resetI18nInstance } from '../../providers/I18nProvider'

// Mock matchMedia for ThemeProvider
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

/**
 * A stateful child component that tracks session state (a counter and a list of items).
 * Also exposes theme toggle and language switch controls.
 */
function StatefulSessionChild() {
  const [counter, setCounter] = useState(0)
  const [items, setItems] = useState<string[]>([])
  const { theme, toggleTheme } = useTheme()
  const { language, setLanguage } = useLanguage()

  return (
    <div>
      <span data-testid="counter">{counter}</span>
      <span data-testid="items">{JSON.stringify(items)}</span>
      <span data-testid="theme">{theme}</span>
      <span data-testid="language">{language}</span>
      <button data-testid="increment" onClick={() => setCounter((c) => c + 1)}>+</button>
      <button data-testid="add-item" onClick={() => setItems((prev) => [...prev, `item-${prev.length}`])}>Add</button>
      <button data-testid="toggle-theme" onClick={toggleTheme}>Toggle Theme</button>
      <button data-testid="set-en" onClick={() => setLanguage('en')}>EN</button>
      <button data-testid="set-fr" onClick={() => setLanguage('fr')}>FR</button>
    </div>
  )
}

function renderWithProviders() {
  return render(
    <ThemeProvider>
      <I18nProvider>
        <StatefulSessionChild />
      </I18nProvider>
    </ThemeProvider>
  )
}

// Action types for preference changes
type PreferenceAction = { type: 'toggle_theme' } | { type: 'set_language'; lang: 'en' | 'fr' }

const preferenceActionArb: fc.Arbitrary<PreferenceAction> = fc.oneof(
  fc.constant({ type: 'toggle_theme' } as PreferenceAction),
  fc.constantFrom('en' as const, 'fr' as const).map((lang) => ({ type: 'set_language', lang } as PreferenceAction))
)

const actionSequenceArb = fc.array(preferenceActionArb, { minLength: 1, maxLength: 4 })

describe('Property 25: UI preference changes preserve session state', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
    mockMatchMedia(false)
    resetI18nInstance()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('switching language or theme preserves all non-preference session state', async () => {
    await fc.assert(
      fc.asyncProperty(
        actionSequenceArb,
        fc.integer({ min: 1, max: 3 }),
        async (actions, initialClicks) => {
          // Reset state for each property run
          cleanup()
          localStorage.clear()
          document.documentElement.classList.remove('dark')
          vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
          mockMatchMedia(false)
          resetI18nInstance()

          renderWithProviders()
          const user = userEvent.setup()

          // Build up session state: increment counter and add items
          for (let i = 0; i < initialClicks; i++) {
            await user.click(screen.getByTestId('increment'))
            await user.click(screen.getByTestId('add-item'))
          }

          // Verify initial session state
          expect(screen.getByTestId('counter').textContent).toBe(String(initialClicks))
          const expectedItems = Array.from({ length: initialClicks }, (_, i) => `item-${i}`)
          expect(screen.getByTestId('items').textContent).toBe(JSON.stringify(expectedItems))

          // Apply each preference action and verify session state is preserved
          for (const action of actions) {
            if (action.type === 'toggle_theme') {
              await user.click(screen.getByTestId('toggle-theme'))
            } else {
              const btnId = action.lang === 'en' ? 'set-en' : 'set-fr'
              await user.click(screen.getByTestId(btnId))
            }

            // Session state must be preserved after each preference change
            expect(screen.getByTestId('counter').textContent).toBe(String(initialClicks))
            expect(screen.getByTestId('items').textContent).toBe(JSON.stringify(expectedItems))
          }
        }
      ),
      { numRuns: 10 }
    )
  }, 30000)
})
