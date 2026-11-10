import {
  BrowserRouter,
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
} from 'react-router'
import styles from './App.module.css'

function AppLayout() {
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
            <span>Not signed in</span>
            <Link to="/login">Sign in</Link>
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
        <p>No account or live data is connected yet.</p>
        <div className={styles.actions}>
          {title === 'Jobs' && (
            <Link className={styles.primaryLink} to="/jobs/new">Preview job submission</Link>
          )}
          {title === 'Sign in' && (
            <Link className={styles.primaryLink} to="/register">Preview registration</Link>
          )}
          {title !== 'Jobs' && (
            <Link className={styles.secondaryLink} to="/jobs">Back to Jobs</Link>
          )}
        </div>
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
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/jobs" replace />} />
          <Route path="jobs" element={<Placeholder title="Jobs" description="A place to submit work and follow its outcome." />} />
          <Route path="jobs/new" element={<Placeholder title="Submit a job" description="Describe the work for an independent worker to process." />} />
          <Route path="jobs/:jobId" element={<Placeholder title="Job details" description="Inspect a job, its result, and its execution attempts." />} />
          <Route path="workers" element={<Placeholder title="Workers" description="A place to register and inspect independent workers." />} />
          <Route path="workers/:workerId" element={<Placeholder title="Worker details" description="Inspect a worker's registration and supported job types." />} />
          <Route path="login" element={<Placeholder title="Sign in" description="Account authentication will be available here." />} />
          <Route path="register" element={<Placeholder title="Create an account" description="Account registration will be available here." />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
