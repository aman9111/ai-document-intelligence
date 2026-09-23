import { useEffect, useState } from 'react'
import Brand from './components/Brand'
import LoginForm from './components/LoginForm'
import RegisterForm from './components/RegisterForm'
import './App.css'

const API_BASE_URL = 'http://localhost:8000'

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
  }, [token])

  function handleLogout() {
    localStorage.removeItem('token')
    setToken(null)
    setUser(null)
  }

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
      <Brand />

      {user ? (
        <>
          <h1>Hi, {user.name} 🌸</h1>
          <p className="subtitle">You're logged in.</p>

          <div className="profile">
            <span className="avatar">{user.name.charAt(0).toUpperCase()}</span>
            <div>
              <p className="profile-name">{user.name}</p>
            </div>
          </div>

          <div className="empty-state">
            <strong>No documents yet</strong>
            Document upload is coming next.
          </div>
        </>
      ) : (
        <p className="subtitle">Loading...</p>
      )}

      <button type="button" className="btn btn-soft" onClick={handleLogout}>
        Log out
      </button>
    </main>
  )
}

export default App
