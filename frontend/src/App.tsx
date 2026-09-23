import { useCallback, useEffect, useState } from 'react'
import Brand from './components/Brand'
import Documents from './components/Documents'
import LoginForm from './components/LoginForm'
import RegisterForm from './components/RegisterForm'
import './App.css'
import { API_BASE_URL } from './api'

interface User {
  id: number
  name: string
  email: string
}

function App() {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem('token'),
  )
  const [user, setUser] = useState<User | null>(null)
  const [authView, setAuthView] = useState<'login' | 'register'>('login')
  const [notice, setNotice] = useState<string | null>(null)

  // useCallback keeps the same function between renders,
  // so child effects that depend on it don't re-run every render
  const handleLogout = useCallback(() => {
    localStorage.removeItem('token')
    setToken(null)
    setUser(null)
  }, [])

  useEffect(() => {
    if (!token) return

    fetch(`${API_BASE_URL}/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => {
        if (!response.ok) throw new Error('Invalid token')
        return response.json()
      })
      .then((data: User) => setUser(data))
      .catch(() => handleLogout())
  }, [token, handleLogout])

  if (!token) {
    if (authView === 'register') {
      return (
        <RegisterForm
          onRegisterSuccess={() => {
            setNotice('Account created! Please log in.')
            setAuthView('login')
          }}
          onSwitchToLogin={() => setAuthView('login')}
        />
      )
    }

    return (
      <LoginForm
        onLoginSuccess={(newToken) => {
          setNotice(null)
          setToken(newToken)
        }}
        onSwitchToRegister={() => {
          setNotice(null)
          setAuthView('register')
        }}
        notice={notice}
      />
    )
  }

  return (
    <main className="card dashboard">
      <header className="dash-header">
        <Brand />
        <div className="dash-user">
          {user && (
            <span className="avatar avatar-sm" title={user.name}>
              {user.name.charAt(0).toUpperCase()}
            </span>
          )}
          <button type="button" className="link-btn" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      {user ? (
        <>
          <h1>Hi, {user.name} 🌸</h1>
          <p className="subtitle">Upload a document to get started.</p>

          <Documents token={token} onUnauthorized={handleLogout} />
        </>
      ) : (
        <p className="subtitle">Loading...</p>
      )}
    </main>
  )
}

export default App
