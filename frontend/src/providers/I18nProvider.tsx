import { createContext, useContext, useCallback, useState, type ReactNode } from 'react'
import i18n from 'i18next'
import { I18nextProvider } from 'react-i18next'
import type { TFunction } from 'i18next'
import en from '../i18n/en.json'
import fr from '../i18n/fr.json'

export type Language = 'en' | 'fr'

const SUPPORTED_LANGUAGES: Language[] = ['en', 'fr']
const STORAGE_KEY = 'intent-language'

interface LanguageContextValue {
  language: Language
  setLanguage: (lang: Language) => void
  t: TFunction
}

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined)

function getBrowserLanguage(): Language {
  if (typeof navigator === 'undefined') return 'en'
  const browserLang = navigator.language.split('-')[0]
  return SUPPORTED_LANGUAGES.includes(browserLang as Language)
    ? (browserLang as Language)
    : 'en'
}

function getInitialLanguage(): Language {
  if (typeof window === 'undefined') return 'en'
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored && SUPPORTED_LANGUAGES.includes(stored as Language)) {
    return stored as Language
  }
  return getBrowserLanguage()
}

function createI18nInstance(initialLang: Language) {
  const instance = i18n.createInstance()
  instance.init({
    resources: {
      en: { translation: en },
      fr: { translation: fr },
    },
    lng: initialLang,
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false,
    },
  })
  return instance
}

// Create a default instance for production use
let i18nInstance = createI18nInstance(getInitialLanguage())

/**
 * Reset the i18n instance. Used in tests to pick up new localStorage / navigator values.
 */
export function resetI18nInstance() {
  i18nInstance = createI18nInstance(getInitialLanguage())
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(
    () => (i18nInstance.language?.split('-')[0] || 'en') as Language
  )

  const setLanguage = useCallback(
    (lang: Language) => {
      i18nInstance.changeLanguage(lang)
      setLanguageState(lang)
      localStorage.setItem(STORAGE_KEY, lang)
    },
    []
  )

  const t = i18nInstance.t.bind(i18nInstance)

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      <I18nextProvider i18n={i18nInstance}>
        {children}
      </I18nextProvider>
    </LanguageContext.Provider>
  )
}

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useLanguage must be used within an I18nProvider')
  }
  return context
}
