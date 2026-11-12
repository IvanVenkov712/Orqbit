import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'
import { ApiError } from './api/client'
import { useAuth } from './auth'
import styles from './App.module.css'

type Job = {
  id: number
  user_id: number
  owner_username: string
  job_type: string
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
  created_at: string
  updated_at: string
}

const statusLabels = { PENDING: 'Pending', RUNNING: 'Running', SUCCEEDED: 'Succeeded', FAILED: 'Failed' }
const filterLabels = { ALL: 'All statuses', ...statusLabels, LOST: 'Lost attempts' }
const statuses = Object.keys(filterLabels) as (keyof typeof filterLabels)[]
const pageSize = 20

export function JobsPage() {
  const { user, request } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const status = statuses.find((value) => value === searchParams.get('status')) ?? 'PENDING'
  const ownerUsername = searchParams.get('owner_username') ?? ''
  const jobType = searchParams.get('job_type') ?? ''
  const createdFrom = searchParams.get('created_from') ?? ''
  const createdBefore = searchParams.get('created_before') ?? ''
  const rawOffset = searchParams.get('offset') ?? '0'
  const offset = /^\d+$/.test(rawOffset) && Number.isSafeInteger(Number(rawOffset)) ? Number(rawOffset) : 0
  const jobs = useQuery({
    queryKey: ['jobs', user?.id, status, ownerUsername, jobType, createdFrom, createdBefore, offset],
    enabled: !!user,
    queryFn: async ({ signal }) => {
      const query = new URLSearchParams({ limit: String(pageSize), offset: String(offset), sort: 'status_updated' })
      if (ownerUsername) query.set('owner_username', ownerUsername)
      if (jobType) query.set('job_type', jobType)
      for (const [key, value] of [['created_from', createdFrom], ['created_before', createdBefore]]) {
        if (value) query.set(key, Number.isNaN(Date.parse(value)) ? value : new Date(value).toISOString())
      }
      if (status === 'LOST') query.set('attempt_status', 'LOST')
      else if (status !== 'ALL') query.set('status', status)
      return request<Job[]>(`/jobs?${query}`, { signal })
    },
    refetchInterval: (query) => query.state.status !== 'error' && query.state.data?.some((job) => job.status === 'PENDING' || job.status === 'RUNNING') ? 3000 : false,
    refetchIntervalInBackground: false,
  })

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const next = new URLSearchParams(searchParams)
    for (const key of ['owner_username', 'job_type', 'created_from', 'created_before']) {
      const value = String(form.get(key) ?? '')
      if (value) next.set(key, value)
      else next.delete(key)
    }
    next.delete('offset')
    setSearchParams(next)
  }

  function changePage(nextOffset: number) {
    const next = new URLSearchParams(searchParams)
    if (nextOffset) next.set('offset', String(nextOffset))
    else next.delete('offset')
    setSearchParams(next)
  }

  return <>
    <div className={styles.pageHeading}>
      <h1>Jobs</h1>
      <p>Browse jobs you can access, including jobs shared by other owners.</p>
      <Link className={styles.primaryLink} to="/jobs/new">Submit a job</Link>
      <nav className={`${styles.navigation} ${styles.actions}`} aria-label="Job statuses">
        {statuses.map((value) => {
          const next = new URLSearchParams(searchParams)
          next.set('status', value)
          next.delete('offset')
          return <Link key={value} to={`/jobs?${next}`} aria-current={status === value ? 'page' : undefined}>{filterLabels[value]}</Link>
        })}
      </nav>
    </div>
    <section className={styles.placeholder} aria-label="Accessible jobs">
      <form key={`${ownerUsername}|${jobType}|${createdFrom}|${createdBefore}`} onSubmit={filter} aria-label="Filter jobs">
        <div className={`${styles.authFields} ${styles.filters}`}>
          <div>
            <label htmlFor="job-owner-filter">Owner username</label>
            <input id="job-owner-filter" name="owner_username" maxLength={16} defaultValue={ownerUsername} placeholder="All accessible owners" aria-describedby="job-owner-help" />
            <small id="job-owner-help">Exact username. Blank includes all accessible owners.</small>
          </div>
          <div>
            <label htmlFor="job-type-filter">Job type</label>
            <input id="job-type-filter" name="job_type" defaultValue={jobType} maxLength={100} placeholder="All types" />
          </div>
          <div>
            <label htmlFor="job-created-from">Created from</label>
            <input id="job-created-from" name="created_from" type="datetime-local" step="1" defaultValue={createdFrom} aria-describedby="job-created-help" />
          </div>
          <div>
            <label htmlFor="job-created-before">Created before</label>
            <input id="job-created-before" name="created_before" type="datetime-local" step="1" defaultValue={createdBefore} aria-describedby="job-created-help" />
          </div>
        </div>
        <p id="job-created-help">Creation times use your local time zone. The upper bound is exclusive.</p>
        <div className={styles.actions}>
          <button type="submit">Apply filters</button>
          <Link to={`/jobs?status=${status}`}>Clear filters</Link>
        </div>
      </form>
      <h2>{filterLabels[status]}</h2>
      {status === 'LOST' && <p>Jobs with at least one lost execution attempt. The job may have retried or finished since that attempt.</p>}
      {jobs.isPending ? <p role="status">Loading jobs…</p> : jobs.isError ? <>
        <p role="alert">{jobs.error instanceof ApiError ? jobs.error.message : 'Unable to load jobs.'}</p>
        <button type="button" onClick={() => { void jobs.refetch() }}>Try again</button>
      </> : jobs.data.length === 0 ? <p>{offset ? 'No more jobs on this page.' : status === 'ALL' || status === 'LOST' ? 'No jobs match these filters.' : `No ${statusLabels[status].toLowerCase()} jobs.`}</p> : <div className={styles.tableContainer}>
        <table className={styles.jobsTable} aria-label="Submitted jobs">
          <thead><tr><th scope="col">Owner</th><th scope="col">Type</th><th scope="col">Status</th><th scope="col">Created</th><th scope="col">Last updated</th></tr></thead>
          <tbody>
            {jobs.data.map((job) => <tr className={styles.jobRow} key={job.id}>
              <td>{job.owner_username}{job.user_id === user?.id ? ' (you)' : ''}</td>
              <td><Link className={styles.jobLink} to={`/jobs/${job.id}`} aria-label={`View job #${job.id}`}>{job.job_type}</Link></td>
              <td>{statusLabels[job.status]}{(job.status === 'FAILED' || status === 'LOST') && <div><Link to={`/jobs/${job.id}${status === 'LOST' ? '/attempts' : ''}`}>{status === 'LOST' ? 'View lost attempts' : 'View error details'}</Link></div>}</td>
              <td><time dateTime={job.created_at}>{new Date(job.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></td>
              <td><time dateTime={job.updated_at}>{new Date(job.updated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></td>
            </tr>)}
          </tbody>
        </table>
      </div>}
      {!jobs.isPending && !jobs.isError && (offset > 0 || jobs.data.length === pageSize) && <nav className={styles.actions} aria-label="Job pages">
        <button type="button" disabled={offset === 0 || jobs.isFetching} onClick={() => changePage(Math.max(0, offset - pageSize))}>Previous jobs</button>
        <button type="button" disabled={jobs.data.length < pageSize || jobs.isFetching} onClick={() => changePage(offset + pageSize)}>Next jobs</button>
      </nav>}
    </section>
  </>
}
