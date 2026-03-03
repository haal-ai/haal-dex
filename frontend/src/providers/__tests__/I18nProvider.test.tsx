import { useState } from 'react'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { I18nProvider, useLanguage, resetI18nInstance } from '../I18nProvider'

const STORAGE_KEY = 'intent-language'

/** Helper component that exposes language context for testing */
function LanguageConsumer() {
  const { language, setLanguage, t } = useLanguage()
  return (
    <div>
      <span data-testid="language">{language}</span>
      <span data-testid="translated">{t('fileUpload.title')}</span>
      <span data-testid="chat-title">{t('chat.title')}</span>
      <button data-testid="set-en" onClick={() => setLanguage('en')}>EN</button>
      <button data-testid="set-fr" onClick={() => setLanguage('fr')}>FR</button>
    </div>
  )
}

function renderWithProvider() {
  return render(
    <I18nProvider>
      <LanguageConsumer />
    </I18nProvider>
  )
}

describe('I18nProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
    resetI18nInstance()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  describe('default language matches browser preference', () => {
    it('defaults to English when browser language is en', () => {
      vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
      resetI18nInstance()
      renderWithProvider()
      expect(screen.getByTestId('language').textContent).toBe('en')
      expect(screen.getByTestId('translated').textContent).toBe('File Upload')
    })

    it('defaults to French when browser language is fr', () => {
      vi.spyOn(navigator, 'language', 'get').mockReturnValue('fr-FR')
      resetI18nInstance()
      renderWithProvider()
      expect(screen.getByTestId('language').textContent).toBe('fr')
      expect(screen.getByTestId('translated').textContent).toBe('Téléversement de fichiers')
    })

    it('falls back to English for unsupported browser language', () => {
      vi.spyOn(navigator, 'language', 'get').mockReturnValue('de-DE')
      resetI18nInstance()
      renderWithProvider()
      expect(screen.getByTestId('language').textContent).toBe('en')
    })
  })

  describe('manual language switching works', () => {
    it('switches from English to French', async () => {
      renderWithProvider()
      expect(screen.getByTestId('language').textContent).toBe('en')
      expect(screen.getByTestId('translated').textContent).toBe('File Upload')

      const user = userEvent.setup()
      await user.click(screen.getByTestId('set-fr'))

      expect(screen.getByTestId('language').textContent).toBe('fr')
      expect(screen.getByTestId('translated').textContent).toBe('Téléversement de fichiers')
    })

    it('switches from French to English', async () => {
      localStorage.setItem(STORAGE_KEY, 'fr')
      resetI18nInstance()
      renderWithProvider()
      expect(screen.getByTestId('language').textContent).toBe('fr')

      const user = userEvent.setup()
      await user.click(screen.getByTestId('set-en'))

      expect(screen.getByTestId('language').textContent).toBe('en')
      expect(screen.getByTestId('translated').textContent).toBe('File Upload')
    })

    it('translates multiple keys correctly in both languages', async () => {
      renderWithProvider()
      expect(screen.getByTestId('chat-title').textContent).toBe('Chat')

      const user = userEvent.setup()
      await user.click(screen.getByTestId('set-fr'))

      expect(screen.getByTestId('chat-title').textContent).toBe('Discussion')
    })
  })

  describe('language persists in localStorage', () => {
    it('saves language to localStorage on switch', async () => {
      renderWithProvider()

      const user = userEvent.setup()
      await user.click(screen.getByTestId('set-fr'))

      expect(localStorage.getItem(STORAGE_KEY)).toBe('fr')
    })

    it('restores language from localStorage on mount', () => {
      localStorage.setItem(STORAGE_KEY, 'fr')
      resetI18nInstance()
      renderWithProvider()
      expect(screen.getByTestId('language').textContent).toBe('fr')
      expect(screen.getByTestId('translated').textContent).toBe('Téléversement de fichiers')
    })

    it('localStorage preference overrides browser language', () => {
      vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
      localStorage.setItem(STORAGE_KEY, 'fr')
      resetI18nInstance()
      renderWithProvider()
      expect(screen.getByTestId('language').textContent).toBe('fr')
    })
  })

  describe('session state is not affected by language changes', () => {
    it('preserves child component state across language switches', async () => {
      function StatefulChild() {
        const [count, setCount] = useState(0)
        const { language, setLanguage, t } = useLanguage()
        return (
          <div>
            <span data-testid="count">{count}</span>
            <span data-testid="child-lang">{language}</span>
            <span data-testid="child-translated">{t('fileUpload.title')}</span>
            <button data-testid="increment" onClick={() => setCount(c => c + 1)}>+</button>
            <button data-testid="child-set-fr" onClick={() => setLanguage('fr')}>FR</button>
            <button data-testid="child-set-en" onClick={() => setLanguage('en')}>EN</button>
          </div>
        )
      }

      render(
        <I18nProvider>
          <StatefulChild />
        </I18nProvider>
      )

      const user = userEvent.setup()

      // Build up some session state
      await user.click(screen.getByTestId('increment'))
      await user.click(screen.getByTestId('increment'))
      await user.click(screen.getByTestId('increment'))
      expect(screen.getByTestId('count').textContent).toBe('3')

      // Switch language to French
      await user.click(screen.getByTestId('child-set-fr'))
      expect(screen.getByTestId('child-lang').textContent).toBe('fr')
      expect(screen.getByTestId('child-translated').textContent).toBe('Téléversement de fichiers')

      // Session state preserved
      expect(screen.getByTestId('count').textContent).toBe('3')

      // Switch back to English
      await user.click(screen.getByTestId('child-set-en'))
      expect(screen.getByTestId('child-lang').textContent).toBe('en')
      expect(screen.getByTestId('child-translated').textContent).toBe('File Upload')
      expect(screen.getByTestId('count').textContent).toBe('3')
    })
  })

  describe('both EN and FR translations are loaded', () => {
    it('has all top-level translation sections in English', () => {
      renderWithProvider()
      expect(screen.getByTestId('translated').textContent).toBe('File Upload')
      expect(screen.getByTestId('chat-title').textContent).toBe('Chat')
    })

    it('has all top-level translation sections in French', async () => {
      renderWithProvider()
      const user = userEvent.setup()
      await user.click(screen.getByTestId('set-fr'))

      expect(screen.getByTestId('translated').textContent).toBe('Téléversement de fichiers')
      expect(screen.getByTestId('chat-title').textContent).toBe('Discussion')
    })
  })

  describe('useLanguage hook', () => {
    it('throws when used outside I18nProvider', () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

      expect(() => {
        render(<LanguageConsumer />)
      }).toThrow('useLanguage must be used within an I18nProvider')

      spy.mockRestore()
    })
  })
})
