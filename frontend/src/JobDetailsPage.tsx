import { useQuery } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router'
import { ApiError } from './api/client'
import { useAuth } from './auth'
import styles from './App.module.css'

type JobStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
type Job = {
  id: number
  user_id: number
  job_type: string
  status: JobStatus
  params: Record<string, unknown>
  result: Record<string, unknown> | null
  error: Record<string, unknown> | null
}

type Attempt = {
  id: number
  attempt_number: number
  status: JobStatus | 'LOST'
  created_at: string
  updated_at: string
  result: Record<string, unknown> | null
  error: Record<string, unknown> | null
}

const statusLabels = {
  PENDING: 'Pending', RUNNING: 'Running', SUCCEEDED: 'Succeeded', FAILED: 'Failed', LOST: 'Lost',
}
const pageSize = 10

export function JobDetailsPage({ history = false }: { history?: boolean }) {
  const { jobId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user, request } = useAuth()
  const validId = /^[1-9]\d*$/.test(jobId) && Number.isSafeInteger(Number(jobId))
  const rawOffset = searchParams.get('offset') ?? '0'
  const offset = history && /^\d+$/.test(rawOffset) && Number.isSafeInteger(Number(rawOffset)) ? Number(rawOffset) : 0
  const limit = history ? pageSize : 1

  const details = useQuery({
    queryKey: ['job-details', user?.id, jobId, limit, offset],
    enabled: validId && !!user,
    queryFn: async ({ signal }) => {
      const job = await request<Job>(`/jobs/${jobId}`, { signal })
      if (job.user_id !== user?.id) throw new ApiError('Job unavailable', 404)
      // Fetch history after the job so a terminal snapshot includes its final attempt.
      let attempts: Attempt[] = []
      let attemptsError: string | null = null
      try {
        attempts = await request<Attempt[]>(`/jobs/${jobId}/attempts?limit=${limit}&offset=${offset}`, { signal })
      } catch (error) {
        signal.throwIfAborted()
        if (error instanceof ApiError && [401, 403, 404].includes(error.status ?? 0)) throw error
        attemptsError = error instanceof ApiError ? error.message : 'Unable to load execution attempts. Please try again.'
      }
      return { job, attempts, attemptsError }
    },
    refetchInterval: (query) => {
      const status = query.state.data?.job.status
      return query.state.status !== 'error' && (status === 'PENDING' || status === 'RUNNING') ? 3000 : false
    },
    refetchIntervalInBackground: false,
  })

  const { job, attempts = [], attemptsError } = details.data ?? {}
  const unavailable = !validId || (details.error instanceof ApiError && [403, 404].includes(details.error.status ?? 0))

  function changePage(nextOffset: number) {
    const next = new URLSearchParams(searchParams)
    if (nextOffset) next.set('offset', String(nextOffset))
    else next.delete('offset')
    setSearchParams(next)
  }

  return <>
    <div className={styles.pageHeading}>
      <Link to="/jobs">Back to Jobs</Link>
      <h1>{history ? 'Attempt history' : 'Job details'}</h1>
      {history ? <Link to={`/jobs/${jobId}`}>Back to job</Link> : <Link to="/jobs/new">Submit another job</Link>}
    </div>
    {unavailable ? <section className={styles.placeholder}>
      <h2>Job unavailable</h2>
      <p>This job could not be found or is not one of your jobs. Check the link or sign in with the account that submitted it.</p>
    </section> : details.isError ? <section className={styles.placeholder}>
      <h2>Unable to load this job</h2>
      <p role="alert">{details.error instanceof ApiError ? details.error.message : 'Please try again.'}</p>
      <button type="button" onClick={() => { void details.refetch() }}>Try again</button>
    </section> : !job ? <p role="status">Loading job details…</p> : <div className={styles.jobDetails}>
      {!history && <><section className={styles.placeholder} aria-label="Job overview">
        <h2>{job.job_type.replace(/[_-]+/g, ' ').replace(/^./, (letter) => letter.toUpperCase())} #{job.id}</h2>
        <p role="status">{statusLabels[job.status]}</p>
        <dl className={styles.metadata}>
          <div><dt>Job</dt><dd>#{job.id}</dd></div>
          <div><dt>Creator</dt><dd>{user?.username} (you)</dd></div>
          <div><dt>Type</dt><dd>{job.job_type}</dd></div>
        </dl>
      </section>
      <section className={styles.placeholder} aria-label="Parameters">
        <h2>Parameters</h2>
        <pre className={styles.json}>{JSON.stringify(job.params, null, 2)}</pre>
      </section>
      <section className={styles.placeholder} aria-label="Outcome">
        <h2>Outcome</h2>
        {job.result !== null && <><h3>Result</h3><pre className={styles.json}>{JSON.stringify(job.result, null, 2)}</pre></>}
        {job.error !== null && <><h3>Error</h3><pre className={styles.json}>{JSON.stringify(job.error, null, 2)}</pre></>}
        {job.result === null && job.error === null && <p>No outcome reported yet.</p>}
      </section></>}
      <section className={styles.placeholder} aria-label={history ? 'Execution attempts' : 'Latest attempt'}>
        <h2>{history ? 'Execution attempts' : 'Latest attempt'}</h2>
        {attemptsError ? <>
          <p role="alert">{attemptsError}</p>
          <button type="button" onClick={() => { void details.refetch() }}>Try again</button>
        </> : <>
          {attempts.length === 0 && <p>{offset ? 'No more execution attempts on this page.' : 'No execution attempts yet.'}</p>}
          {(history ? attempts : attempts.slice(0, 1)).map((attempt) => <article className={styles.attempt} key={attempt.id} aria-label={`Attempt ${attempt.attempt_number}`}>
            <h3>Attempt {attempt.attempt_number}</h3>
            <p>{statusLabels[attempt.status]}</p>
            <dl className={styles.metadata}>
              <div><dt>Started</dt><dd><time dateTime={attempt.created_at}>{new Date(attempt.created_at).toLocaleString()}</time></dd></div>
              <div><dt>Last updated</dt><dd><time dateTime={attempt.updated_at}>{new Date(attempt.updated_at).toLocaleString()}</time></dd></div>
            </dl>
            {attempt.result !== null && <><h4>Result</h4><pre className={styles.json}>{JSON.stringify(attempt.result, null, 2)}</pre></>}
            {attempt.error !== null && <><h4>Error</h4><pre className={styles.json}>{JSON.stringify(attempt.error, null, 2)}</pre></>}
          </article>)}
        </>}
        {!history && attempts.length > 0 && <div className={styles.actions}>
          <Link className={styles.secondaryLink} to={`/jobs/${jobId}/attempts`}>View attempt history</Link>
        </div>}
        {history && <nav className={styles.actions} aria-label="Attempt pages">
          <button type="button" disabled={offset === 0 || details.isFetching} onClick={() => changePage(Math.max(0, offset - pageSize))}>Previous attempts</button>
          <button type="button" disabled={!!attemptsError || attempts.length < pageSize || details.isFetching} onClick={() => changePage(offset + pageSize)}>Next attempts</button>
        </nav>}
      </section>
    </div>}
  </>
}
