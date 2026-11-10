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
import { ParameterEditor, readParameters } from './ParameterEditor'
import type { Parameter } from './ParameterEditor'
import orqbitIcon from './assets/orqbit-icon.svg'
import styles from './App.module.css'

function AppLayout() {
  const { user, logout, restoring, restoreError } = useAuth()
  return (
    <div className={styles.app}>
      <a className={styles.skipLink} href="#main-content">Skip to content</a>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link className={styles.brand} to="/jobs" aria-label="Orqbit home">
            <img src={orqbitIcon} alt="" width="36" height="36" />
            Orqbit
          </Link>
          <nav className={styles.navigation} aria-label="Main navigation">
            <NavLink to="/jobs">Jobs</NavLink>
            <NavLink to="/workers">Workers</NavLink>
          </nav>
          <div className={styles.userArea} role="group" aria-label="Current user">
            {restoring ? <span>Checking session…</span> : restoreError ? <span>Session unavailable</span> : user ? <>
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
        <p>You are signed in. This screen does not load live data yet.</p>
        <div className={styles.actions}>
          {title === 'Jobs' && (
            <Link className={styles.primaryLink} to="/jobs/new">Submit a job</Link>
          )}
          {title !== 'Jobs' && (
            <Link className={styles.secondaryLink} to="/jobs">Back to Jobs</Link>
          )}
        </div>
      </section>
    </>
  )
}

function SessionStatus() {
  const { restoreError, restore, logout } = useAuth()
  return (
    <section className={styles.placeholder}>
      {restoreError ? <>
        <h1>Unable to open your workspace</h1>
        <p role="alert">{restoreError.message}</p>
        <button type="button" onClick={() => { void restore() }}>Try again</button>
      </> : <p role="status">Restoring your session…</p>}
      <div className={styles.actions}>
        <button type="button" onClick={logout}>Sign out</button>
      </div>
    </section>
  )
}

function RequireAuth() {
  const { user, restoring, restoreError } = useAuth()
  const location = useLocation()
  if (restoring || restoreError) return <SessionStatus />
  return user ? <Outlet /> : <Navigate to="/login" replace state={{ from: location.pathname + location.search + location.hash }} />
}

function AuthPage({ register = false }: { register?: boolean }) {
  const { user, login, expired, restoring, restoreError } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [error, setError] = useState<ApiError | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => { pending.current?.abort() }, [])

  // Only return to a local application route, never an arbitrary redirect URL.
  const from = location.state?.from
  const destination = typeof from === 'string' && /^\/(jobs|workers)(\/|\?|#|$)/.test(from) ? from : '/jobs'
  if (restoring || restoreError) return <SessionStatus />
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
      <img className={styles.authIcon} src={orqbitIcon} alt="" width="56" height="56" />
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
      <Link to={register ? '/login' : '/register'} state={{ from }}>
        {register ? 'Already have an account? Sign in' : 'Create an account'}
      </Link>
    </section>
  )
}

type JobSubmission = {
  key: string
  payload: { job_type: string; params: Record<string, unknown>; permission_policy: 'PRIVATE' }
}

function SubmitJobPage() {
  const { request } = useAuth()
  const navigate = useNavigate()
  const [submission, setSubmission] = useState<JobSubmission | null>(null)
  const [parameters, setParameters] = useState<Parameter[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => { pending.current?.abort() }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current) return
    let intended = submission
    if (!intended) {
      const form = new FormData(event.currentTarget)
      const jobType = String(form.get('job_type') ?? '')
      if (!jobType.trim() || jobType.length > 100) {
        setError(new ApiError('Enter a job type of 1–100 characters, including a non-whitespace character.', null, [
          { loc: ['job_type'], msg: 'Enter a non-blank job type of at most 100 characters.', type: 'value_error' },
        ]))
        return
      }
      let params: Record<string, unknown>
      try {
        params = readParameters(parameters)
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : 'Check the parameter names and values.'
        setError(new ApiError(message, null, [
          { loc: ['params'], msg: message, type: 'value_error' },
        ]))
        return
      }
      // Keep this exact payload with its key until an explicit new submission.
      intended = {
        key: crypto.randomUUID(),
        payload: { job_type: jobType, params, permission_policy: 'PRIVATE' },
      }
      setSubmission(intended)
    }
    const controller = new AbortController()
    pending.current = controller
    setSubmitting(true)
    setError(null)
    try {
      const job = await request<{ id: number }>('/jobs/', {
        method: 'POST', json: intended.payload,
        headers: { 'Idempotency-Key': intended.key }, signal: controller.signal,
      })
      if (!Number.isSafeInteger(job?.id) || job.id <= 0) {
        throw new ApiError('Orqbit returned an invalid job response. Retry the same submission.', null)
      }
      if (!controller.signal.aborted) navigate(`/jobs/${job.id}`)
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(cause instanceof ApiError ? cause : new ApiError('Unable to submit the job. Please retry the same submission.', null))
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

  const uncertain = submission && error && (error.status === null || error.status < 400 || error.status === 408 || error.status >= 500)
  return (
    <>
      <div className={styles.pageHeading}>
        <p className={styles.eyebrow}>Jobs</p>
        <h1>Submit a job</h1>
        <p>Describe the work for an independent worker to process.</p>
      </div>
      <section className={styles.placeholder} aria-label="Job submission">
        {error && <div className={styles.formError} role="alert">{error.message}</div>}
        {submission && error && <p role="status">
          {uncertain && 'The job may already have been created. Keep this page open to retry safely. '}
          Retry sends the same request with the same submission key. To change the request, start a new submission.
          {uncertain && ' A new submission could create another job.'}
        </p>}
        <form onSubmit={submit} aria-label="Submit a job" aria-busy={submitting}>
          <fieldset className={styles.authFields} disabled={submitting || submission !== null}>
            <div>
              <label htmlFor="job-type">Job type</label>
              <input id="job-type" name="job_type" required maxLength={100}
                aria-invalid={!!fieldError('job_type')} aria-describedby="job-type-help job-type-error" />
              <small id="job-type-help">Use the exact type supported by your worker, for example add_numbers. Spaces are preserved.</small>
              <small id="job-type-error">{fieldError('job_type')}</small>
            </div>
            <fieldset className={styles.parameterGroup} aria-label="Parameters"
              aria-invalid={!!fieldError('params')} aria-describedby="job-params-help job-params-error">
              <legend>Parameters</legend>
              <p id="job-params-help">Add named parameters and choose each value's type. Objects contain named fields; lists contain ordered items.</p>
              <ParameterEditor parameters={parameters} onChange={setParameters} />
              <small id="job-params-error">{fieldError('params')}</small>
            </fieldset>
            <div>
              <label htmlFor="job-policy">Access policy</label>
              <select id="job-policy" name="permission_policy" aria-describedby="job-policy-help job-policy-error"
                aria-invalid={!!fieldError('permission_policy')}>
                <option value="PRIVATE">Private</option>
              </select>
              <small id="job-policy-help">Only you can read this job. Only your workers with a matching job type can claim it.</small>
              <small id="job-policy-error">{fieldError('permission_policy')}</small>
            </div>
          </fieldset>
          <div className={styles.actions}>
            <button type="submit" disabled={submitting}>{submitting ? 'Submitting…' : submission ? 'Retry submission' : 'Submit job'}</button>
            {submission && <button type="button" disabled={submitting} onClick={() => {
              setSubmission(null)
              setError(null)
            }}>Start a new submission</button>}
          </div>
        </form>
        <div className={styles.actions}><Link to="/jobs">Back to Jobs</Link></div>
      </section>
    </>
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
              <Route path="jobs/new" element={<SubmitJobPage />} />
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
