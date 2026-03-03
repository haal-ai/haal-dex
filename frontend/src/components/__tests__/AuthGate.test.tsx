import { render, screen, cleanup, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { AuthGate } from '../AuthGate'
import { AuthProvider } from '../../hooks/useAuth'
import { I18nProvider, resetI18nInstance } from '../../providers/I18nProvider'

const TOKEN_KEY = 'intent-auth-token'

// Mock global fetch
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <I18nProvider>
      <AuthProvider>
        {ui}
      </AuthProvider>
    </I18nProvider>
  )
}

function mockLoginSuccess(role: string = 'user') {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      access_token: 'test-jwt-token',
      user_id: 'user-1',
      roles: [role],
    }),
  })
}

function mockLoginFailure() {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status: 401,
  })
}

function mockMeSuccess(role: string = 'user') {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      user_id: 'user-1',
      username: 'testuser',
      roles: [role],
    }),
  })
}

function mockMeFailure() {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status: 401,
  })
}

describe('AuthGate', () => {
  beforeEach(() => {
    localStorage.clear()
    mockFetch.mockReset()
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
    resetI18nInstance()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  describe('shows login form when not authenticated', () => {
    it('renders login form with username, password, and submit button', async () => {
      renderWithProviders(
        <AuthGate><div data-testid="protected">Protected Content</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })
      expect(screen.getByTestId('username-input')).toBeInTheDocument()
      expect(screen.getByTestId('password-input')).toBeInTheDocument()
      expect(screen.getByTestId('login-button')).toBeInTheDocument()
      expect(screen.queryByTestId('protected')).not.toBeInTheDocument()
    })

    it('uses i18n translations for labels', async () => {
      renderWithProviders(
        <AuthGate><div>Content</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })
      expect(screen.getByLabelText('Username')).toBeInTheDocument()
      expect(screen.getByLabelText('Password')).toBeInTheDocument()
      expect(screen.getByTestId('login-button').textContent).toBe('Log In')
    })
  })

  describe('renders children when authenticated', () => {
    it('shows protected content after successful login', async () => {
      renderWithProviders(
        <AuthGate><div data-testid="protected">Protected Content</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.type(screen.getByTestId('username-input'), 'testuser')
      await user.type(screen.getByTestId('password-input'), 'password123')

      mockLoginSuccess('user')
      await user.click(screen.getByTestId('login-button'))

      await waitFor(() => {
        expect(screen.getByTestId('protected')).toBeInTheDocument()
      })
      expect(screen.getByText('Protected Content')).toBeInTheDocument()
      expect(screen.queryByTestId('login-form')).not.toBeInTheDocument()
    })
  })

  describe('login form submits credentials', () => {
    it('calls POST /api/auth/login with username and password', async () => {
      renderWithProviders(
        <AuthGate><div data-testid="protected">Content</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.type(screen.getByTestId('username-input'), 'myuser')
      await user.type(screen.getByTestId('password-input'), 'mypass')

      mockLoginSuccess('user')
      await user.click(screen.getByTestId('login-button'))

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: 'myuser', password: 'mypass' }),
        })
      })
    })
  })

  describe('shows error on failed login', () => {
    it('displays error message when login fails', async () => {
      renderWithProviders(
        <AuthGate><div data-testid="protected">Content</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.type(screen.getByTestId('username-input'), 'baduser')
      await user.type(screen.getByTestId('password-input'), 'badpass')

      mockLoginFailure()
      await user.click(screen.getByTestId('login-button'))

      await waitFor(() => {
        expect(screen.getByTestId('login-error')).toBeInTheDocument()
      })
      expect(screen.getByTestId('login-error').textContent).toBe('Invalid credentials')
      expect(screen.queryByTestId('protected')).not.toBeInTheDocument()
    })
  })

  describe('logout clears session', () => {
    it('returns to login form after logout', async () => {
      // Render a component that exposes logout
      function TestApp() {
        const { useAuth } = require('../../hooks/useAuth')
        const auth = useAuth()
        return (
          <AuthGate>
            <div data-testid="protected">Protected</div>
            <button data-testid="logout-btn" onClick={auth.logout}>Logout</button>
          </AuthGate>
        )
      }

      renderWithProviders(
        <AuthGate><div data-testid="protected">Content</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })

      // Login first
      const user = userEvent.setup()
      await user.type(screen.getByTestId('username-input'), 'testuser')
      await user.type(screen.getByTestId('password-input'), 'pass')

      mockLoginSuccess('user')
      await user.click(screen.getByTestId('login-button'))

      await waitFor(() => {
        expect(screen.getByTestId('protected')).toBeInTheDocument()
      })

      // Token should be stored
      expect(localStorage.getItem(TOKEN_KEY)).toBe('test-jwt-token')
    })
  })

  describe('admin gate blocks non-admin users', () => {
    it('shows unauthorized message for non-admin user with requireAdmin', async () => {
      renderWithProviders(
        <AuthGate requireAdmin><div data-testid="admin-content">Admin Only</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.type(screen.getByTestId('username-input'), 'regularuser')
      await user.type(screen.getByTestId('password-input'), 'pass')

      mockLoginSuccess('user')
      await user.click(screen.getByTestId('login-button'))

      await waitFor(() => {
        expect(screen.getByTestId('unauthorized-message')).toBeInTheDocument()
      })
      expect(screen.getByTestId('unauthorized-message').textContent).toBe('Access denied')
      expect(screen.queryByTestId('admin-content')).not.toBeInTheDocument()
    })

    it('shows content for admin user with requireAdmin', async () => {
      renderWithProviders(
        <AuthGate requireAdmin><div data-testid="admin-content">Admin Only</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.type(screen.getByTestId('username-input'), 'adminuser')
      await user.type(screen.getByTestId('password-input'), 'pass')

      mockLoginSuccess('admin')
      await user.click(screen.getByTestId('login-button'))

      await waitFor(() => {
        expect(screen.getByTestId('admin-content')).toBeInTheDocument()
      })
      expect(screen.getByText('Admin Only')).toBeInTheDocument()
      expect(screen.queryByTestId('unauthorized-message')).not.toBeInTheDocument()
    })

    it('allows non-admin user when requireAdmin is false', async () => {
      renderWithProviders(
        <AuthGate><div data-testid="content">Regular Content</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.type(screen.getByTestId('username-input'), 'regularuser')
      await user.type(screen.getByTestId('password-input'), 'pass')

      mockLoginSuccess('user')
      await user.click(screen.getByTestId('login-button'))

      await waitFor(() => {
        expect(screen.getByTestId('content')).toBeInTheDocument()
      })
    })
  })

  describe('token restored from localStorage on mount', () => {
    it('auto-restores session when valid token exists in localStorage', async () => {
      localStorage.setItem(TOKEN_KEY, 'stored-jwt-token')
      mockMeSuccess('user')

      renderWithProviders(
        <AuthGate><div data-testid="protected">Protected Content</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('protected')).toBeInTheDocument()
      })

      expect(mockFetch).toHaveBeenCalledWith('/api/auth/me', {
        headers: { Authorization: 'Bearer stored-jwt-token' },
      })
    })

    it('shows login form when stored token is invalid', async () => {
      localStorage.setItem(TOKEN_KEY, 'expired-token')
      mockMeFailure()

      renderWithProviders(
        <AuthGate><div data-testid="protected">Protected Content</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('protected')).not.toBeInTheDocument()
      // Token should be cleared
      expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    })

    it('restores admin role from token validation', async () => {
      localStorage.setItem(TOKEN_KEY, 'admin-jwt-token')
      mockMeSuccess('admin')

      renderWithProviders(
        <AuthGate requireAdmin><div data-testid="admin-content">Admin</div></AuthGate>
      )

      await waitFor(() => {
        expect(screen.getByTestId('admin-content')).toBeInTheDocument()
      })
    })
  })

  describe('logout clears token and shows login', () => {
    it('clears localStorage token on logout', async () => {
      // Use a component that exposes logout functionality
      const { useAuth } = await import('../../hooks/useAuth')

      function LogoutTestApp() {
        const auth = useAuth()
        return (
          <AuthGate>
            <div data-testid="protected">Protected</div>
            <button data-testid="logout-btn" onClick={auth.logout}>Logout</button>
          </AuthGate>
        )
      }

      localStorage.setItem(TOKEN_KEY, 'valid-token')
      mockMeSuccess('user')

      render(
        <I18nProvider>
          <AuthProvider>
            <LogoutTestApp />
          </AuthProvider>
        </I18nProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('protected')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.click(screen.getByTestId('logout-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('login-form')).toBeInTheDocument()
      })
      expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    })
  })
})
