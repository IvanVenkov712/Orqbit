import { Fragment, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router'
import { ApiError } from './api/client'
import { useAuth } from './auth'
import { Icon } from './Icon'
import { GroupedRows, ListControls, SortHeading } from './ListControls'
import type { ListFilter } from './ListControls'
import styles from './App.module.css'

type Worker = {
  id: number
  name: string
  user_id: number
  owner_username: string
  active: boolean
  supported_types: string[]
  permission_policy: 'PRIVATE' | 'PERMITTED_USERS' | 'ALL'
  permitted_user_ids: number[]
}

const pageSize = 20
const visibilityLabels = { PRIVATE: 'Private', PERMITTED_USERS: 'Permitted users', ALL: 'All users' }
const credentialHelp = 'Active describes credential/registration status. It does not establish that a worker process is online.'
const sorts = [
  { value: '', label: 'Newest registered' },
  { value: 'created_desc', label: 'Recently created' }, { value: 'created_asc', label: 'Oldest first' },
  { value: 'name_asc', label: 'Name · A to Z' }, { value: 'name_desc', label: 'Name · Z to A' },
  { value: 'owner_asc', label: 'Owner · A to Z' }, { value: 'owner_desc', label: 'Owner · Z to A' },
  { value: 'active_desc', label: 'Active credentials first' }, { value: 'active_asc', label: 'Inactive credentials first' },
]
const groups = [{ value: 'active', label: 'Group by credential status' }, { value: 'owner', label: 'Group by owner' }, { value: 'visibility', label: 'Group by visibility' }]
const filters: ListFilter[] = [
  { key: 'owner_username', label: 'Owner username', placeholder: 'e.g. alex', maxLength: 16 },
  { key: 'job_type', label: 'Supported job type', placeholder: 'e.g. add_numbers', maxLength: 100 },
  { key: 'active', label: 'Credential/registration status', options: [{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }] },
  { key: 'created_from', label: 'Created from', type: 'datetime-local' },
  { key: 'created_before', label: 'Created before', type: 'datetime-local' },
]

export function WorkersPage() {
  const { user, request } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const jobType = searchParams.get('job_type') ?? ''
  const ownerUsername = searchParams.get('owner_username') ?? ''
  const active = ['true', 'false'].includes(searchParams.get('active') ?? '') ? searchParams.get('active')! : ''
  const createdFrom = searchParams.get('created_from') ?? ''
  const createdBefore = searchParams.get('created_before') ?? ''
  const sort = sorts.find(({ value }) => value === searchParams.get('sort'))?.value ?? ''
  const group = groups.find(({ value }) => value === searchParams.get('group'))?.value ?? ''
  const rawOffset = searchParams.get('offset') ?? '0'
  const offset = /^\d+$/.test(rawOffset) && Number.isSafeInteger(Number(rawOffset)) ? Number(rawOffset) : 0
  const workers = useQuery({
    queryKey: ['workers', user?.id, jobType, ownerUsername, active, createdFrom, createdBefore, sort, offset],
    enabled: !!user,
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) => {
      const query = new URLSearchParams({ limit: String(pageSize), offset: String(offset) })
      if (sort) query.set('sort', sort)
      if (ownerUsername) query.set('owner_username', ownerUsername)
      if (jobType) query.set('job_type', jobType)
      if (active) query.set('active', active)
      for (const [key, value] of [['created_from', createdFrom], ['created_before', createdBefore]]) {
        if (value) query.set(key, Number.isNaN(Date.parse(value)) ? value : new Date(value).toISOString())
      }
      return request<Worker[]>(`/workers?${query}`, { signal })
    },
  })

  function changePage(nextOffset: number) {
    const next = new URLSearchParams(searchParams)
    if (nextOffset) next.set('offset', String(nextOffset))
    else next.delete('offset')
    setSearchParams(next)
  }

  function changeSort(value: string) {
    const next = new URLSearchParams(searchParams)
    next.set('sort', value)
    next.delete('offset')
    setSearchParams(next)
  }

  return <>
    <div className={styles.collectionHeading}>
      <div><p className={styles.eyebrow}>WORKSPACE / WORKER DIRECTORY</p><h1>Workers</h1>
        <p>The independent engines behind your work.</p></div>
      <div className={styles.inlineActions}><button className={styles.iconButton} type="button" aria-label="Refresh workers" title="Refresh workers" disabled={workers.isFetching} onClick={() => { void workers.refetch() }}><Icon name="refresh" /></button>
        <Link className={styles.primaryLink} to="/workers/new"><Icon name="plus" size={17} />Register a worker</Link></div>
    </div>
    <div className={styles.collectionIntro}><Icon name="workers" size={15} />Capability-based workers<span>Browse your registrations and shared workers</span></div>
    <section className={styles.collection} aria-label="Accessible workers" aria-busy={workers.isFetching}>
      <ListControls resource="workers" filters={filters} sorts={sorts} defaultSort="" groups={groups}>
        <button type="button" className={styles.quickFilter} aria-pressed={ownerUsername === user?.username} onClick={() => {
          const next = new URLSearchParams(searchParams)
          if (ownerUsername === user?.username) next.delete('owner_username')
          else next.set('owner_username', user!.username)
          next.delete('offset')
          setSearchParams(next)
        }}>My workers</button>
      </ListControls>
      <div className={styles.resultsHeading}><h2>Worker directory</h2><span>{workers.data ? `${workers.data.length} on this page` : 'Worker collection'}</span></div>
      {workers.isPending ? <div className={styles.emptyState}><span className={styles.loadingMark} /><p role="status">Loading workers…</p></div> : workers.isError ? <div className={styles.emptyState}>
        <p role="alert">{workers.error instanceof ApiError ? workers.error.message : 'Unable to load workers.'}</p>
        <button type="button" onClick={() => { void workers.refetch() }}>Try again</button>
      </div> : workers.data.length === 0 ? <div className={styles.emptyState}><span className={styles.emptyIcon}><Icon name="workers" size={28} /></span><h3>Room for another engine.</h3><p>{offset ? 'No more workers on this page.' : 'No accessible workers match these filters.'}</p><span>Adjust your filters or register an independent worker.</span></div> : <div className={styles.tableContainer}>
        <table className={styles.jobsTable} data-resource="workers" aria-label="Registered workers">
          <thead><tr>
            <SortHeading label="Name" ascending="name_asc" descending="name_desc" current={sort} onSort={changeSort} />
            <SortHeading label="Owner" ascending="owner_asc" descending="owner_desc" current={sort} onSort={changeSort} />
            <th scope="col">Supported types</th>
            <SortHeading label="Credential/registration status" ascending="active_asc" descending="active_desc" current={sort} onSort={changeSort} />
            <th scope="col">Visibility</th>
          </tr></thead>
          <GroupedRows key={`${group}:${offset}`} items={workers.data} group={group} columns={5}
            groupLabel={(worker) => group === 'active' ? worker.active ? 'Active credentials' : 'Inactive credentials' : group === 'owner' ? worker.owner_username : visibilityLabels[worker.permission_policy]}
            renderRow={(worker) => <tr className={styles.jobRow} key={worker.id}>
              <td><Link className={styles.jobLink} to={`/workers/${worker.id}`}>{worker.name}</Link><span className={styles.recordId}>#{worker.id}</span></td>
              <td><span className={styles.ownerCell}><span className={styles.smallAvatar} aria-hidden="true">{worker.owner_username.slice(0, 2).toUpperCase()}</span><span>{worker.owner_username}{worker.user_id === user?.id ? ' (you)' : ''}</span></span></td>
              <td><span className={styles.typeTags}>{worker.supported_types.map((type, index) => <Fragment key={type}><span className={styles.typeTag}>{type}</span>{index < worker.supported_types.length - 1 ? ', ' : ''}</Fragment>)}</span></td>
              <td><span className={styles.statusBadge} data-status={worker.active ? 'SUCCEEDED' : 'PENDING'}>{worker.active ? 'Active' : 'Inactive'}</span></td>
              <td><span className={styles.visibility}>{visibilityLabels[worker.permission_policy]}</span></td>
            </tr>} />
        </table>
      </div>}
      <p className={styles.credentialNote}>{credentialHelp}</p>
      {!workers.isPending && !workers.isError && (offset > 0 || workers.data.length === pageSize) && <nav className={styles.pagination} aria-label="Worker pages">
        <span>Page {Math.floor(offset / pageSize) + 1}<span className={styles.pageSize}>20 per page</span></span>
        <div className={styles.inlineActions}><button className={styles.controlButton} type="button" disabled={offset === 0 || workers.isFetching} onClick={() => changePage(Math.max(0, offset - pageSize))}>Previous workers</button>
        <button className={styles.controlButton} type="button" disabled={workers.data.length < pageSize || workers.isFetching} onClick={() => changePage(offset + pageSize)}>Next workers<Icon name="arrow" size={15} /></button></div>
      </nav>}
    </section>
  </>
}

export function WorkerDetailsPage() {
  const { workerId = '' } = useParams()
  const { user, request } = useAuth()
  const validId = /^[1-9]\d*$/.test(workerId) && Number.isSafeInteger(Number(workerId))
  const details = useQuery({
    queryKey: ['worker-details', user?.id, workerId],
    enabled: validId && !!user,
    queryFn: ({ signal }) => request<Worker>(`/workers/${workerId}`, { signal }),
  })
  const worker = details.data
  const unavailable = !validId || (details.error instanceof ApiError && [403, 404].includes(details.error.status ?? 0))

  return <>
    <div className={styles.pageHeading}>
      <Link to="/workers">Back to Workers</Link>
      <h1>Worker details</h1>
    </div>
    {unavailable ? <section className={styles.placeholder}>
      <h2>Worker unavailable</h2>
      <p>This worker could not be found or you do not have permission to view it.</p>
    </section> : details.isError ? <section className={styles.placeholder}>
      <p role="alert">{details.error instanceof ApiError ? details.error.message : 'Unable to load this worker.'}</p>
      <button type="button" onClick={() => { void details.refetch() }}>Try again</button>
    </section> : !worker ? <p role="status">Loading worker details…</p> : <section className={styles.placeholder} aria-label="Worker metadata">
      <h2>{worker.name}</h2>
      <dl className={styles.metadata}>
        <div><dt>Worker ID</dt><dd>#{worker.id}</dd></div>
        <div><dt>Owner</dt><dd>{worker.owner_username}{worker.user_id === user?.id ? ' (you)' : ''}</dd></div>
        <div><dt>Credential/registration status</dt><dd>{worker.active ? 'Active' : 'Inactive'}</dd></div>
        <div><dt>Visibility</dt><dd>{visibilityLabels[worker.permission_policy]}</dd></div>
        {worker.permission_policy === 'PERMITTED_USERS' && <div><dt>Permitted user IDs</dt><dd>{worker.permitted_user_ids.join(', ') || 'None'}</dd></div>}
      </dl>
      <p>{credentialHelp}</p>
      <h3>Supported types</h3>
      <ul>{worker.supported_types.map((type) => <li key={type}>{type}</li>)}</ul>
    </section>}
  </>
}

export function RegisterWorkerPage() {
  const { user, request } = useAuth()
  const queryClient = useQueryClient()
  // The creation response (including its key) belongs only to this mounted screen.
  const [created, setCreated] = useState<(Worker & { secret_api_key: string }) | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [policy, setPolicy] = useState<Worker['permission_policy']>('PRIVATE')
  const [copyStatus, setCopyStatus] = useState('')
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => { pending.current?.abort() }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current || created) return
    const form = new FormData(event.currentTarget)
    const name = String(form.get('name') ?? '')
    const supportedTypes = [...new Set(String(form.get('supported_types') ?? '').split(/\r?\n/))]
    if (!/^[a-zA-Z0-9_-]{3,16}$/.test(name)) {
      setError(new ApiError('Choose a name of 3–16 letters, digits, underscores or hyphens.', null, [
        { loc: ['name'], msg: 'Use 3–16 letters, digits, underscores or hyphens.', type: 'value_error' },
      ]))
      return
    }
    if (supportedTypes.some((type) => !type.trim() || type.length > 100)) {
      setError(new ApiError('Enter one non-blank supported type per line, each at most 100 characters.', null, [
        { loc: ['supported_types'], msg: 'Remove blank lines and keep each type within 100 characters.', type: 'value_error' },
      ]))
      return
    }
    let permittedUserIds: number[] | undefined
    if (policy === 'PERMITTED_USERS') {
      const input = String(form.get('permitted_user_ids') ?? '').trim()
      const values = input ? input.split(/[,\s]+/) : []
      if (values.some((value) => !/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) <= 0)) {
        const message = 'Enter positive whole-number IDs separated by commas or whitespace.'
        setError(new ApiError(message, null, [{ loc: ['permitted_user_ids'], msg: message, type: 'value_error' }]))
        return
      }
      permittedUserIds = [...new Set(values.map(Number))]
    }
    const controller = new AbortController()
    pending.current = controller
    setSubmitting(true)
    setError(null)
    try {
      const worker = await request<Worker & { secret_api_key: string }>('/workers', {
        method: 'POST', json: {
          name, supported_types: supportedTypes, permission_policy: policy,
          ...(permittedUserIds !== undefined ? { permitted_user_ids: permittedUserIds } : {}),
        }, signal: controller.signal,
      })
      if (!Number.isSafeInteger(worker?.id) || worker.id <= 0 || worker.user_id !== user!.id || !worker.secret_api_key) {
        throw new ApiError('Orqbit returned an invalid registration response.', null)
      }
      if (!controller.signal.aborted) {
        setCreated(worker)
        void queryClient.invalidateQueries({ queryKey: ['workers', user!.id] })
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(cause instanceof ApiError ? cause : new ApiError('Unable to register this worker. Please try again.', null))
      }
    } finally {
      if (!controller.signal.aborted) {
        pending.current = null
        setSubmitting(false)
      }
    }
  }

  function fieldError(name: string) {
    if (name === 'name' && error?.status === 409) return 'This worker name is already taken. Choose a different name.'
    return error?.fieldErrors.filter(({ loc }) => loc.includes(name)).map(({ msg }) => msg).join(' ')
  }

  async function copyKey() {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.secret_api_key)
      setCopyStatus('API key copied. Save it securely for your independent worker.')
    } catch {
      setCopyStatus('Unable to copy. Select the API key above and copy it manually.')
    }
  }

  return <>
    <div className={styles.pageHeading}>
      <Link to="/workers">Back to Workers</Link>
      <h1>Register a worker</h1>
    </div>
    <section className={styles.placeholder} aria-label={created ? 'Worker registered' : 'Worker registration'}>
      {created ? <>
        <h2>{created.name} registered</h2>
        <p>Save this API key now. It is shown only here, once, and cannot be retrieved after leaving or reloading this page.</p>
        <p>Store it securely in your independent worker's configuration. The example add_numbers worker uses the API_KEY setting in its environment or private .env file. The worker sends it in the X-API-Key header. Do not commit it to source control.</p>
        <h3>API key</h3>
        <pre className={styles.json} aria-label="New worker API key">{created.secret_api_key}</pre>
        <button type="button" onClick={() => { void copyKey() }}>Copy API key</button>
        {copyStatus && <p role="status">{copyStatus}</p>}
        <div className={styles.actions}><Link to={`/workers/${created.id}`}>I've saved the key — view worker</Link></div>
      </> : <>
        {error && <div className={styles.formError} role="alert">{error.status === 409 ? 'This worker name is already taken. Choose a different name.' : error.message}</div>}
        {error && error.fieldErrors.length === 0 && (error.status === null || error.status >= 500 || error.status === 408) && <p>The registration may have succeeded, but its API key was not received. Check your workers before retrying. Existing keys cannot be retrieved.</p>}
        <form onSubmit={submit} aria-label="Register a worker" aria-busy={submitting}>
          <fieldset className={styles.authFields} disabled={submitting}>
            <div>
              <label htmlFor="worker-name">Worker name</label>
              <input id="worker-name" name="name" required minLength={3} maxLength={16} pattern="[a-zA-Z0-9_\-]{3,16}" autoComplete="off"
                aria-invalid={!!fieldError('name')} aria-describedby="worker-name-help worker-name-error" />
              <small id="worker-name-help">3–16 letters, digits, underscores or hyphens. Names must be unique.</small>
              <small id="worker-name-error">{fieldError('name')}</small>
            </div>
            <div>
              <label htmlFor="worker-types">Supported types</label>
              <textarea id="worker-types" name="supported_types" required rows={4}
                aria-invalid={!!fieldError('supported_types')} aria-describedby="worker-types-help worker-types-error" />
              <small id="worker-types-help">One exact job type per line, for example add_numbers. Each type needs 1–100 characters. Spaces are preserved.</small>
              <small id="worker-types-error">{fieldError('supported_types')}</small>
            </div>
            <div>
              <label htmlFor="worker-policy">Visibility policy</label>
              <select id="worker-policy" name="permission_policy" value={policy}
                onChange={(event) => { setPolicy(event.target.value as Worker['permission_policy']); setError(null) }}
                aria-describedby="worker-policy-help worker-policy-error" aria-invalid={!!fieldError('permission_policy')}>
                {Object.entries(visibilityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <small id="worker-policy-help">Worker metadata visibility: {policy === 'PRIVATE'
                ? "Only you can view this worker's metadata."
                : policy === 'PERMITTED_USERS'
                  ? "You and the listed users can view this worker's metadata."
                  : "Any authenticated user can view this worker's metadata."} Visibility does not reveal the API key or allow others to claim as this worker. Job access policies determine which jobs it can claim.</small>
              <small id="worker-policy-error">{fieldError('permission_policy')}</small>
            </div>
            {policy === 'PERMITTED_USERS' && <div>
              <label htmlFor="worker-user-ids">Permitted user IDs</label>
              <input id="worker-user-ids" name="permitted_user_ids" aria-invalid={!!fieldError('permitted_user_ids')}
                aria-describedby="worker-user-ids-help worker-user-ids-error" />
              <small id="worker-user-ids-help">Existing user IDs, separated by commas or whitespace. Grants metadata visibility only. Leave blank for no additional user grants.</small>
              <small id="worker-user-ids-error">{fieldError('permitted_user_ids')}</small>
            </div>}
            <button type="submit">{submitting ? 'Registering…' : 'Register worker'}</button>
          </fieldset>
        </form>
      </>}
    </section>
  </>
}
