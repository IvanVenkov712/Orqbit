import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'
import { ApiError } from './api/client'
import { useAuth } from './auth'
import styles from './App.module.css'

type Job = {
  id: number
  user_id: number
  job_type: string
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
  created_at: string
  updated_at: string
}

const statusLabels = { PENDING: 'Pending', RUNNING: 'Running', SUCCEEDED: 'Succeeded', FAILED: 'Failed' }
const statuses = Object.keys(statusLabels) as Job['status'][]
const pageSize = 20

export function JobsPage() {
  const { user, request } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const status = statuses.find((value) => value === searchParams.get('status')) ?? 'PENDING'
  const rawOffset = searchParams.get('offset') ?? '0'
  const offset = /^\d+$/.test(rawOffset) && Number.isSafeInteger(Number(rawOffset)) ? Number(rawOffset) : 0
  const jobs = useQuery({
    queryKey: ['jobs', user?.id, status, offset],
    enabled: !!user,
    queryFn: async ({ signal }) => {
      const page = await request<Job[]>(`/jobs?owner_id=${user!.id}&limit=${pageSize}&offset=${offset}&sort=status_updated&status=${status}`, { signal })
      return page.filter((job) => job.user_id === user!.id && job.status === status)
    },
    refetchInterval: (query) => query.state.status !== 'error' && query.state.data?.some((job) => job.status === 'PENDING' || job.status === 'RUNNING') ? 3000 : false,
    refetchIntervalInBackground: false,
  })

  function changePage(nextOffset: number) {
    const next = new URLSearchParams(searchParams)
    if (nextOffset) next.set('offset', String(nextOffset))
    else next.delete('offset')
    setSearchParams(next)
  }

  return <>
    <div className={styles.pageHeading}>
      <h1>Jobs</h1>
      <Link className={styles.primaryLink} to="/jobs/new">Submit a job</Link>
      <nav className={`${styles.navigation} ${styles.actions}`} aria-label="Job statuses">
        {statuses.map((value) => {
          const next = new URLSearchParams(searchParams)
          next.set('status', value)
          next.delete('offset')
          return <Link key={value} to={`/jobs?${next}`} aria-current={status === value ? 'page' : undefined}>{statusLabels[value]}</Link>
        })}
      </nav>
    </div>
    <section className={styles.placeholder} aria-label="Your jobs">
      <h2>{statusLabels[status]}</h2>
      {jobs.isPending ? <p role="status">Loading jobs…</p> : jobs.isError ? <>
        <p role="alert">{jobs.error instanceof ApiError ? jobs.error.message : 'Unable to load jobs.'}</p>
        <button type="button" onClick={() => { void jobs.refetch() }}>Try again</button>
      </> : jobs.data.length === 0 ? <p>{offset ? 'No more jobs on this page.' : `No ${statusLabels[status].toLowerCase()} jobs.`}</p> : <div className={styles.tableContainer}>
        <table className={styles.jobsTable} aria-label="Submitted jobs">
          <thead><tr><th scope="col">Owner</th><th scope="col">Type</th><th scope="col">Status</th><th scope="col">Created</th><th scope="col">Last updated</th></tr></thead>
          <tbody>
            {jobs.data.map((job) => <tr className={styles.jobRow} key={job.id}>
              <td>{user?.username}</td>
              <td><Link className={styles.jobLink} to={`/jobs/${job.id}`} aria-label={`View job #${job.id}`}>{job.job_type}</Link></td>
              <td>{statusLabels[job.status]}</td>
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
