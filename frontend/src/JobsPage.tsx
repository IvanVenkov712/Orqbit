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
}

const statusLabels = { PENDING: 'Pending', RUNNING: 'Running', SUCCEEDED: 'Succeeded', FAILED: 'Failed' }
const pageSize = 20

export function JobsPage() {
  const { user, request } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const rawOffset = searchParams.get('offset') ?? '0'
  const offset = /^\d+$/.test(rawOffset) && Number.isSafeInteger(Number(rawOffset)) ? Number(rawOffset) : 0
  const jobs = useQuery({
    queryKey: ['jobs', user?.id, offset],
    enabled: !!user,
    queryFn: async ({ signal }) => {
      const page = await request<Job[]>(`/jobs?owner_id=${user!.id}&limit=${pageSize}&offset=${offset}`, { signal })
      return page.filter((job) => job.user_id === user!.id)
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
    </div>
    <section className={styles.placeholder} aria-label="Your jobs">
      {jobs.isPending ? <p role="status">Loading jobs…</p> : jobs.isError ? <>
        <p role="alert">{jobs.error instanceof ApiError ? jobs.error.message : 'Unable to load jobs.'}</p>
        <button type="button" onClick={() => { void jobs.refetch() }}>Try again</button>
      </> : jobs.data.length === 0 ? <p>{offset ? 'No more jobs on this page.' : 'No jobs submitted yet.'}</p> : <div className={styles.tableContainer}>
        <table className={styles.jobsTable} aria-label="Submitted jobs">
          <thead><tr><th scope="col">Owner</th><th scope="col">Name</th><th scope="col">Type</th><th scope="col">Status</th></tr></thead>
          <tbody>{jobs.data.map((job) => <tr className={styles.jobRow} key={job.id}>
            <td>{user?.username}</td>
            <td><Link className={styles.jobLink} to={`/jobs/${job.id}`}>
              {job.job_type.replace(/[_-]+/g, ' ').replace(/^./, (letter) => letter.toUpperCase())} #{job.id}
            </Link></td>
            <td>{job.job_type}</td>
            <td>{statusLabels[job.status]}</td>
          </tr>)}</tbody>
        </table>
      </div>}
      {!jobs.isPending && !jobs.isError && (offset > 0 || jobs.data.length === pageSize) && <nav className={styles.actions} aria-label="Job pages">
        <button type="button" disabled={offset === 0 || jobs.isFetching} onClick={() => changePage(Math.max(0, offset - pageSize))}>Previous jobs</button>
        <button type="button" disabled={jobs.data.length < pageSize || jobs.isFetching} onClick={() => changePage(offset + pageSize)}>Next jobs</button>
      </nav>}
    </section>
  </>
}
