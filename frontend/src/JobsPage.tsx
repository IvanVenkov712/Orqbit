import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'
import { ApiError } from './api/client'
import { useAuth } from './auth'
import { Icon } from './Icon'
import { GroupedRows, ListControls, SortHeading } from './ListControls'
import type { ListFilter } from './ListControls'
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
const sorts = [
  { value: 'status_updated', label: 'Lifecycle order' },
  { value: 'status_desc', label: 'Status · reversed' },
  { value: 'created_desc', label: 'Newest first' }, { value: 'created_asc', label: 'Oldest first' },
  { value: 'updated_desc', label: 'Recently updated' }, { value: 'updated_asc', label: 'Least recently updated' },
  { value: 'type_asc', label: 'Type · A to Z' }, { value: 'type_desc', label: 'Type · Z to A' },
  { value: 'owner_asc', label: 'Owner · A to Z' }, { value: 'owner_desc', label: 'Owner · Z to A' },
]
const groups = [{ value: 'status', label: 'Group by status' }, { value: 'job_type', label: 'Group by type' }, { value: 'owner', label: 'Group by owner' }]
const filters: ListFilter[] = [
  { key: 'owner_username', label: 'Owner username', placeholder: 'e.g. alex', maxLength: 16 },
  { key: 'job_type', label: 'Job type', placeholder: 'e.g. add_numbers', maxLength: 100 },
  { key: 'created_from', label: 'Created from', type: 'datetime-local' },
  { key: 'created_before', label: 'Created before', type: 'datetime-local' },
]

export function JobsPage() {
  const { user, request } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const status = statuses.find((value) => value === searchParams.get('status')) ?? 'PENDING'
  const ownerUsername = searchParams.get('owner_username') ?? ''
  const jobType = searchParams.get('job_type') ?? ''
  const createdFrom = searchParams.get('created_from') ?? ''
  const createdBefore = searchParams.get('created_before') ?? ''
  const sort = sorts.find(({ value }) => value === searchParams.get('sort'))?.value ?? 'status_updated'
  const group = groups.find(({ value }) => value === searchParams.get('group'))?.value ?? ''
  const rawOffset = searchParams.get('offset') ?? '0'
  const offset = /^\d+$/.test(rawOffset) && Number.isSafeInteger(Number(rawOffset)) ? Number(rawOffset) : 0
  const jobs = useQuery({
    queryKey: ['jobs', user?.id, status, ownerUsername, jobType, createdFrom, createdBefore, sort, offset],
    enabled: !!user,
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) => {
      const query = new URLSearchParams({ limit: String(pageSize), offset: String(offset), sort })
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

  function changeSort(value: string) {
    const next = new URLSearchParams(searchParams)
    next.set('sort', value)
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
    <div className={styles.collectionHeading}>
      <div><p className={styles.eyebrow}>WORKSPACE / JOB QUEUE</p><h1>Jobs</h1></div>
      <div className={styles.inlineActions}><button className={styles.iconButton} type="button" aria-label="Refresh jobs" title="Refresh jobs" disabled={jobs.isFetching} onClick={() => { void jobs.refetch() }}><Icon name="refresh" /></button>
        <Link className={styles.primaryLink} to="/jobs/new"><Icon name="plus" size={17} />Submit a job</Link></div>
    </div>
    <section className={styles.collection} aria-label="Accessible jobs" aria-busy={jobs.isFetching}>
      <nav className={styles.statusTabs} aria-label="Job statuses">
        {statuses.map((value) => {
          const next = new URLSearchParams(searchParams)
          next.set('status', value)
          next.delete('offset')
          return <Link key={value} to={`/jobs?${next}`} aria-current={status === value ? 'page' : undefined}>{filterLabels[value]}</Link>
        })}
      </nav>
      <ListControls resource="jobs" filters={filters} sorts={sorts} defaultSort="status_updated" groups={groups}>
        <button type="button" className={styles.quickFilter} aria-pressed={ownerUsername === user?.username} onClick={() => {
          const next = new URLSearchParams(searchParams)
          if (ownerUsername === user?.username) next.delete('owner_username')
          else next.set('owner_username', user!.username)
          next.delete('offset')
          setSearchParams(next)
        }}>My jobs</button>
      </ListControls>
      <div className={styles.resultsHeading}><h2>{filterLabels[status]}</h2><span>{jobs.data ? `${jobs.data.length} on this page` : 'Job collection'}</span></div>
      {status === 'LOST' && <p className={styles.groupNotice}>Jobs with at least one lost execution attempt. The job may have retried or finished since that attempt.</p>}
      {jobs.isPending ? <div className={styles.emptyState}><span className={styles.loadingMark} /><p role="status">Loading jobs…</p></div> : jobs.isError ? <div className={styles.emptyState}>
        <p role="alert">{jobs.error instanceof ApiError ? jobs.error.message : 'Unable to load jobs.'}</p>
        <button type="button" onClick={() => { void jobs.refetch() }}>Try again</button>
      </div> : jobs.data.length === 0 ? <div className={styles.emptyState}><span className={styles.emptyIcon}><Icon name="jobs" size={28} /></span><h3>A little breathing room.</h3><p>{offset ? 'No more jobs on this page.' : status === 'ALL' || status === 'LOST' ? 'No jobs match these filters.' : `No ${statusLabels[status].toLowerCase()} jobs.`}</p><span>Try a different view or submit something new.</span></div> : <div className={styles.tableContainer}>
        <table className={styles.jobsTable} data-resource="jobs" aria-label="Submitted jobs">
          <thead><tr>
            <SortHeading label="Owner" ascending="owner_asc" descending="owner_desc" current={sort} onSort={changeSort} />
            <SortHeading label="Type" ascending="type_asc" descending="type_desc" current={sort} onSort={changeSort} />
            <SortHeading label="Status" ascending="status_updated" descending="status_desc" current={sort} onSort={changeSort} />
            <SortHeading label="Created" ascending="created_asc" descending="created_desc" current={sort} onSort={changeSort} />
            <SortHeading label="Last updated" ascending="updated_asc" descending="updated_desc" current={sort} onSort={changeSort} />
          </tr></thead>
          <GroupedRows key={`${group}:${offset}:${status}`} items={jobs.data} group={group} columns={5}
            groupLabel={(job) => group === 'status' ? statusLabels[job.status] : group === 'owner' ? job.owner_username : job.job_type}
            renderRow={(job) => <tr className={styles.jobRow} key={job.id}>
              <td><span className={styles.ownerCell}><span className={styles.smallAvatar} aria-hidden="true">{job.owner_username.slice(0, 2).toUpperCase()}</span><span>{job.owner_username}{job.user_id === user?.id ? ' (you)' : ''}</span></span></td>
              <td><Link className={styles.jobLink} to={`/jobs/${job.id}`} aria-label={`View job #${job.id}`}>{job.job_type}</Link><span className={styles.recordId}>#{job.id}</span></td>
              <td><span className={styles.statusBadge} data-status={job.status}>{statusLabels[job.status]}</span>{(job.status === 'FAILED' || status === 'LOST') && <div className={styles.diagnosticLink}><Link to={`/jobs/${job.id}${status === 'LOST' ? '/attempts' : ''}`}>{status === 'LOST' ? 'View lost attempts' : 'View error details'}<span aria-hidden="true"> ↗</span></Link></div>}</td>
              <td data-label="Created"><time dateTime={job.created_at}>{new Date(job.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></td>
              <td data-label="Last updated"><time dateTime={job.updated_at}>{new Date(job.updated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></td>
            </tr>} />
        </table>
      </div>}
      {!jobs.isPending && !jobs.isError && (offset > 0 || jobs.data.length === pageSize) && <nav className={styles.pagination} aria-label="Job pages">
        <span>Page {Math.floor(offset / pageSize) + 1}<span className={styles.pageSize}>20 per page</span></span>
        <div className={styles.inlineActions}><button className={styles.controlButton} type="button" disabled={offset === 0 || jobs.isFetching} onClick={() => changePage(Math.max(0, offset - pageSize))}>Previous jobs</button>
        <button className={styles.controlButton} type="button" disabled={jobs.data.length < pageSize || jobs.isFetching} onClick={() => changePage(offset + pageSize)}>Next jobs<Icon name="arrow" size={15} /></button></div>
      </nav>}
    </section>
  </>
}
