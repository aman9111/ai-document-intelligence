import { useState } from 'react'
import type { FormEvent } from 'react'
import Brand from './Brand'

const API_BASE_URL = 'http://localhost:8000'

interface LoginResponse {
  access_token: string
  token_type: string
  user: {
    id: number
    name: string
    email: string
  }
}

interface LoginFormProps {
  onLoginSuccess: (token: string) => void
  onSwitchToRegister: () => void
  notice?: string | null
}

function LoginForm({ onLoginSuccess, onSwitchToRegister, notice }: LoginFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      const response = await fetch(`${API_BASE_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })

      const data = await response.json()

      if (!response.ok) {
        setError(data.detail ?? 'Login failed')
        return
      }

      const loginData = data as LoginResponse
      localStorage.setItem('token', loginData.access_token)
      onLoginSuccess(loginData.access_token)
    } catch {
      setError('Could not reach the server')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="card">
      <Brand />
      <h1>Welcome back 👋</h1>
      <p className="subtitle">Log in to chat with your documents.</p>

      {notice && <p className="login-notice">{notice}</p>}

      <form onSubmit={handleSubmit} className="login-form">
        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        {error && <p className="login-error">{error}</p>}

        <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
          {isSubmitting ? 'Logging in...' : 'Log in'}
        </button>
      </form>

      <p className="switch-auth">
        New here?{' '}
        <button type="button" className="link-btn" onClick={onSwitchToRegister}>
          Create an account
        </button>
      </p>
    </main>
  )
}

export default LoginForm
