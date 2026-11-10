import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, apiRequest } from './api/client'

type User = {
  id: number
  username: string
  email: string
  full_name: string
  active: boolean
  role: 'ADMIN' | 'REGULAR'
}

type Session = {
  token: string
  user: User | null
  expiresAt: number
  controller: AbortController
}

type Auth = {
  user: User | null
  expired: boolean
  restoring: boolean
  restoreError: ApiError | null
  restore: () => Promise<void>
  login: (username: string, password: string, signal: AbortSignal) => Promise<void>
  logout: () => void
  request: typeof apiRequest
}

const AuthContext = createContext<Auth | null>(null)
const expiryMessage = 'Your session has expired. Please sign in again.'
const storageKey = 'orqbit.access_token'

// The server verifies the JWT. Reading exp here only schedules local sign-out.
function tokenExpiry(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    if (typeof payload.exp === 'number' && Number.isFinite(payload.exp * 1000)) {
      return payload.exp * 1000
    }
  } catch { /* Use a safe error for an invalid token response. */ }
  throw new ApiError('Orqbit returned an invalid session. Please try signing in again.', null)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const sessionRef = useRef<Session | null>(null)
  const [expired, setExpired] = useState(false)
  const [restoring, setRestoring] = useState(true)
  const [restoreError, setRestoreError] = useState<ApiError | null>(null)

  function endSession(didExpire = false) {
    sessionRef.current?.controller.abort()
    sessionRef.current = null
    setSession(null)
    setExpired(didExpire)
    setRestoring(false)
    setRestoreError(null)
    localStorage.removeItem(storageKey)
  }

  async function restore() {
    setRestoring(true)
    setRestoreError(null)
    let current: Session | undefined
    try {
      const token = localStorage.getItem(storageKey)
      if (!token) return
      let expiresAt: number
      try {
        expiresAt = tokenExpiry(token)
      } catch {
        endSession(true)
        return
      }
      if (expiresAt <= Date.now()) {
        endSession(true)
        return
      }
      sessionRef.current?.controller.abort()
      current = { token, user: null, expiresAt, controller: new AbortController() }
      sessionRef.current = current
      setSession(current)
      const user = await apiRequest<User>('/users/me/', { token, signal: current.controller.signal })
      current.controller.signal.throwIfAborted()
      if (expiresAt <= Date.now()) {
        endSession(true)
        return
      }
      const restored = { ...current, user }
      sessionRef.current = restored
      setSession(restored)
      setExpired(false)
    } catch (error) {
      if (current?.controller.signal.aborted) return
      if (error instanceof ApiError && [401, 403].includes(error.status ?? 0)) {
        endSession(true)
      } else {
        setRestoreError(error instanceof ApiError ? error : new ApiError('Unable to restore your session. Please try again.', null))
      }
    } finally {
      if (!current?.controller.signal.aborted) setRestoring(false)
    }
  }

  async function login(username: string, password: string, signal: AbortSignal) {
    const { access_token: token } = await apiRequest<{ access_token: string }>('/auth/login', {
      method: 'POST', form: new URLSearchParams({ username, password }), signal,
    })
    signal.throwIfAborted()
    const user = await apiRequest<User>('/users/me/', { token, signal })
    signal.throwIfAborted()
    const expiresAt = tokenExpiry(token)
    if (expiresAt <= Date.now()) throw new ApiError(expiryMessage, 401)
    try {
      localStorage.setItem(storageKey, token)
    } catch {
      throw new ApiError('Unable to save your session. Allow site storage and try again.', null)
    }
    sessionRef.current?.controller.abort()
    const nextSession = { token, user, expiresAt, controller: new AbortController() }
    sessionRef.current = nextSession
    setSession(nextSession)
    setExpired(false)
    setRestoreError(null)
  }

  async function request<T>(path: string, options: Parameters<typeof apiRequest>[1] = {}): Promise<T> {
    const current = sessionRef.current
    if (!current || !current.user || current.expiresAt <= Date.now()) {
      endSession(true)
      throw new ApiError(expiryMessage, 401)
    }
    try {
      return await apiRequest<T>(path, {
        ...options,
        token: current.token,
        signal: options.signal
          ? AbortSignal.any([options.signal, current.controller.signal])
          : current.controller.signal,
      })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401 && sessionRef.current === current) {
        endSession(true)
      }
      throw error
    }
  }

  useEffect(() => {
    if (!session) return
    const expiresAt = session.expiresAt
    let timer: ReturnType<typeof setTimeout>
    function checkExpiry() {
      const remaining = expiresAt - Date.now()
      if (remaining <= 0) {
        endSession(true)
      } else {
        clearTimeout(timer)
        timer = setTimeout(checkExpiry, Math.min(remaining, 2_147_483_647))
      }
    }
    checkExpiry()
    window.addEventListener('focus', checkExpiry)
    document.addEventListener('visibilitychange', checkExpiry)
    return () => {
      clearTimeout(timer)
      window.removeEventListener('focus', checkExpiry)
      document.removeEventListener('visibilitychange', checkExpiry)
    }
  }, [session])

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- Restore external browser storage and validate it with the API.
    void restore()
    return () => { sessionRef.current?.controller.abort() }
  }, [])

  return (
    <AuthContext.Provider value={{ user: session?.user ?? null, expired, restoring, restoreError, restore, login, logout: () => endSession(), request }}>
      {children}
    </AuthContext.Provider>
  )
}

// oxlint-disable-next-line react/only-export-components -- Keep the small context and its hook together.
export function useAuth() {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside AuthProvider')
  return auth
}
