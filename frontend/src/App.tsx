import { useCallback, useEffect, useState } from 'react'
import Brand from './components/Brand'
import Documents from './components/Documents'
import { IconLogout, IconSearch } from './components/Icons'
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
  const [search, setSearch] = useState('')
  const [accountOpen, setAccountOpen] = useState(false)

  // useCallback keeps the same function between renders,
  // so child effects that depend on it don't re-run every render
  const handleLogout = useCallback(() => {
    localStorage.removeItem('token')
    setToken(null)
    setUser(null)
    setAccountOpen(false)
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
    <div className="workspace">
      <header className="ws-header">
        <Brand />
        <label className="ws-search">
          <IconSearch />
          <span className="sr-only">Search your documents</span>
          <input
            type="search"
            placeholder="Search your documents"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        {user && (
          <div className="menu-wrap">
            <button
              type="button"
              className="avatar avatar-sm avatar-btn"
              aria-label={`Account: ${user.name}`}
              aria-haspopup="menu"
              aria-expanded={accountOpen}
              onClick={() => setAccountOpen((open) => !open)}
            >
              {user.name.charAt(0).toUpperCase()}
            </button>
            {accountOpen && (
              <>
                <button type="button" className="menu-scrim" aria-label="Close menu" onClick={() => setAccountOpen(false)} />
                <div className="menu" role="menu">
                  <div className="menu-user">
                    <strong>{user.name}</strong>
                    <span>{user.email}</span>
                  </div>
                  <span className="menu-divider" />
                  <button type="button" role="menuitem" onClick={handleLogout}>
                    <IconLogout size={16} /> Log out
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </header>

      {user ? (
        <Documents token={token} search={search} onUnauthorized={handleLogout} />
      ) : (
        <p className="side-note ws-loading">Loading...</p>
      )}
    </div>
  )
}

export default App
