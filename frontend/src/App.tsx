import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  BrowserRouter,
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router'
import { ApiError, apiRequest } from './api/client'
import { AuthProvider, useAuth } from './auth'
import styles from './App.module.css'

function AppLayout() {
  const { user, logout } = useAuth()
  return (
    <div className={styles.app}>
      <a className={styles.skipLink} href="#main-content">Skip to content</a>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link className={styles.brand} to="/jobs" aria-label="Orqbit home">
            <img src="/favicon.svg" alt="" width="32" height="32" />
            Orqbit
          </Link>
          <nav className={styles.navigation} aria-label="Main navigation">
            <NavLink to="/jobs">Jobs</NavLink>
            <NavLink to="/workers">Workers</NavLink>
          </nav>
          <div className={styles.userArea} role="group" aria-label="Current user">
            {user ? <>
              <span>{user.full_name || user.username} (@{user.username})</span>
              <button type="button" onClick={logout}>Sign out</button>
            </> : <>
              <span>Not signed in</span>
              <Link to="/login">Sign in</Link>
            </>}
          </div>
        </div>
      </header>

      <main id="main-content" className={styles.main} tabIndex={-1}>
        <Outlet />
      </main>

      <footer className={styles.footer}>
        Orqbit · Asynchronous job processing
      </footer>
    </div>
  )
}

function Placeholder({ title, description }: { title: string; description: string }) {
  return (
    <>
      <div className={styles.pageHeading}>
        <p className={styles.eyebrow}>Workspace</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <section className={styles.placeholder} aria-label={`${title} placeholder`}>
        <span className={styles.badge}>Planned screen</span>
        <h2>This space is taking shape</h2>
        <p>
          This is a placeholder. {title} functionality will be added in a later
          step of the frontend roadmap.
        </p>
        <p>You are signed in. Live job and worker data is not connected yet.</p>
        <div className={styles.actions}>
          {title === 'Jobs' && (
            <Link className={styles.primaryLink} to="/jobs/new">Preview job submission</Link>
          )}
          {title !== 'Jobs' && (
            <Link className={styles.secondaryLink} to="/jobs">Back to Jobs</Link>
          )}
        </div>
      </section>
    </>
  )
}

function RequireAuth() {
  const { user } = useAuth()
  const location = useLocation()
  return user ? <Outlet /> : <Navigate to="/login" replace state={{ from: location.pathname + location.search + location.hash }} />
}

function AuthPage({ register = false }: { register?: boolean }) {
  const { user, login, expired } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [error, setError] = useState<ApiError | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => { pending.current?.abort() }, [])

  // Only return to a local application route, never an arbitrary redirect URL.
  const from = location.state?.from
  const destination = typeof from === 'string' && /^\/(jobs|workers)(\/|\?|#|$)/.test(from) ? from : '/jobs'
  if (user) return <Navigate to={destination} replace />

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current) return
    const form = new FormData(event.currentTarget)
    const username = String(form.get('username'))
    const password = String(form.get('password'))
    const controller = new AbortController()
    pending.current = controller
    setSubmitting(true)
    setError(null)
    try {
      if (register) {
        await apiRequest('/auth/register', {
          method: 'POST',
          json: { username, password, email: String(form.get('email')), full_name: String(form.get('full_name')) },
          signal: controller.signal,
        })
        if (!controller.signal.aborted) navigate('/login', { replace: true, state: { registered: true, from } })
      } else {
        await login(username, password, controller.signal)
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(cause instanceof ApiError ? cause : new ApiError('Unable to sign in. Please try again.', null))
      }
    } finally {
      if (!controller.signal.aborted) {
        pending.current = null
        setSubmitting(false)
      }
    }
  }

  function fieldError(name: string) {
    return error?.fieldErrors.filter(({ loc }) => loc.includes(name)).map(({ msg }) => msg).join(' ')
  }

  return (
    <section className={styles.authPanel}>
      <p className={styles.eyebrow}>Your Orqbit workspace</p>
      <h1>{register ? 'Create an account' : 'Sign in'}</h1>
      <p>{register ? 'Register an account, then sign in to your workspace.' : 'Sign in with your username to access Jobs and Workers.'}</p>
      {!register && expired && <p role="status">Your session has expired. Please sign in again.</p>}
      {!register && location.state?.registered && <p role="status">Account created. Sign in with your new credentials.</p>}
      {error && <div className={styles.formError} role="alert">{error.message}</div>}
      <form onSubmit={submit} aria-busy={submitting}>
        <fieldset className={styles.authFields} disabled={submitting}>
          <div>
            <label htmlFor="username">Username</label>
            <input id="username" name="username" autoComplete="username" required
              minLength={register ? 3 : undefined} maxLength={register ? 16 : undefined}
              pattern={register ? '[a-zA-Z0-9_\\-]{3,16}' : undefined}
              aria-invalid={!!fieldError('username')} aria-describedby={register ? 'username-help username-error' : undefined} />
            {register && <small id="username-help">3–16 letters, digits, underscores or hyphens.</small>}
            <small id="username-error">{fieldError('username')}</small>
          </div>
          {register && <>
            <div>
              <label htmlFor="email">Email</label>
              <input id="email" name="email" type="email" autoComplete="email" required
                aria-invalid={!!fieldError('email')} aria-describedby="email-error" />
              <small id="email-error">{fieldError('email')}</small>
            </div>
            <div>
              <label htmlFor="full-name">Full name</label>
              <input id="full-name" name="full_name" autoComplete="name" required
                aria-invalid={!!fieldError('full_name')} aria-describedby="full-name-error" />
              <small id="full-name-error">{fieldError('full_name')}</small>
            </div>
          </>}
          <div>
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} required
              minLength={register ? 6 : undefined} maxLength={register ? 20 : undefined}
              aria-invalid={!!fieldError('password')} aria-describedby={register ? 'password-help password-error' : 'password-error'} />
            {register && <small id="password-help">6–20 characters: uppercase and lowercase letters, a digit, and one of @$#%. Use only letters, digits and those symbols.</small>}
            <small id="password-error">{fieldError('password')}</small>
          </div>
          <button type="submit">{submitting ? (register ? 'Creating account…' : 'Signing in…') : (register ? 'Create account' : 'Sign in')}</button>
        </fieldset>
      </form>
      <p className={styles.authNote}>Your session stays in memory. Refreshing this page requires signing in again.</p>
      <Link to={register ? '/login' : '/register'} state={{ from }}>
        {register ? 'Already have an account? Sign in' : 'Create an account'}
      </Link>
    </section>
  )
}

function NotFound() {
  return (
    <section className={styles.placeholder}>
      <p className={styles.eyebrow}>404</p>
      <h1>Page not found</h1>
      <p>This address does not match an Orqbit page. Return to Jobs to continue.</p>
      <Link className={styles.primaryLink} to="/jobs">Back to Jobs</Link>
    </section>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/jobs" replace />} />
            <Route element={<RequireAuth />}>
              <Route path="jobs" element={<Placeholder title="Jobs" description="A place to submit work and follow its outcome." />} />
              <Route path="jobs/new" element={<Placeholder title="Submit a job" description="Describe the work for an independent worker to process." />} />
              <Route path="jobs/:jobId" element={<Placeholder title="Job details" description="Inspect a job, its result, and its execution attempts." />} />
              <Route path="workers" element={<Placeholder title="Workers" description="A place to register and inspect independent workers." />} />
              <Route path="workers/:workerId" element={<Placeholder title="Worker details" description="Inspect a worker's registration and supported job types." />} />
            </Route>
            <Route path="login" element={<AuthPage key="login" />} />
            <Route path="register" element={<AuthPage key="register" register />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
