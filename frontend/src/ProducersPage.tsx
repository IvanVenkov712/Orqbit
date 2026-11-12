import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { ApiError } from './api/client'
import { useAuth } from './auth'
import { Icon } from './Icon'
import styles from './App.module.css'

type Producer = { id: number; name: string; user_id: number; owner_username: string; active: boolean }
const namePattern = /^[a-zA-Z0-9_-]{3,16}$/
const validId = (value: string) => /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value))

export function ProducersPage() {
  const { user, request } = useAuth()
  const [params, setParams] = useSearchParams()
  const lookup = ['id', 'name'].includes(params.get('lookup') ?? '') ? params.get('lookup')! : ''
  const query = params.get('query') ?? ''
  const limit = ['20', '50', '100'].includes(params.get('limit') ?? '') ? Number(params.get('limit')) : 20
  const rawOffset = params.get('offset') ?? '0'
  const offset = /^\d+$/.test(rawOffset) && Number.isSafeInteger(Number(rawOffset)) ? Number(rawOffset) : 0
  const invalid = lookup === 'id' ? !validId(query) : lookup === 'name' ? !namePattern.test(query) : query.length > 16
  const producers = useQuery({
    queryKey: ['producers', user?.id, lookup, query, limit, offset],
    enabled: !!user && !invalid,
    queryFn: async ({ signal }) => {
      if (lookup) return [await request<Producer>(lookup === 'id' ? `/producers/${query}` : `/producers/by-name/${encodeURIComponent(query)}`, { signal })]
      const search = new URLSearchParams({ limit: String(limit), offset: String(offset) })
      if (query) search.set('query', query)
      return request<Producer[]>(`/producers?${search}`, { signal })
    },
  })

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const next = new URLSearchParams()
    for (const key of ['lookup', 'query', 'limit']) {
      const value = String(form.get(key) ?? '')
      if (value) next.set(key, value)
    }
    setParams(next)
  }

  function changePage(nextOffset: number) {
    const next = new URLSearchParams(params)
    if (nextOffset) next.set('offset', String(nextOffset))
    else next.delete('offset')
    setParams(next)
  }

  return <>
    <div className={styles.collectionHeading}>
      <div><p className={styles.eyebrow}>WORKSPACE / PRODUCERS</p><h1>Producers</h1><p>Manage the applications that submit your jobs.</p></div>
      <div className={styles.inlineActions}>
        <button className={styles.iconButton} type="button" aria-label="Refresh producers" disabled={invalid || producers.isFetching} onClick={() => { void producers.refetch() }}><Icon name="refresh" /></button>
        <Link className={styles.primaryLink} to="/producers/new"><Icon name="plus" size={17} />Create a producer</Link>
      </div>
    </div>
    <section className={styles.collection} aria-label="Your producers" aria-busy={producers.isFetching}>
      <div className={styles.resultsHeading}><h2>Producer directory</h2><span>Owned by your account</span></div>
      <form key={params.toString()} className={styles.filterPanel} onSubmit={search} aria-label="Search producers">
        <div className={`${styles.authFields} ${styles.filters}`}>
          <div><label htmlFor="producer-lookup">Search by</label><select id="producer-lookup" name="lookup" defaultValue={lookup}>
            <option value="">Name contains</option><option value="name">Exact name</option><option value="id">Producer ID</option>
          </select></div>
          <div><label htmlFor="producer-query">Producer name or ID</label><input id="producer-query" name="query" defaultValue={query} aria-describedby="producer-search-help" /></div>
          <div><label htmlFor="producer-limit">Producers per page</label><select id="producer-limit" name="limit" defaultValue={limit}>
            {[20, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
          </select></div>
        </div>
        <div className={styles.filterFooter}><small id="producer-search-help">Name contains is case-insensitive (up to 16 characters). Exact names use 3–16 letters, digits, underscores or hyphens. IDs are positive whole numbers.</small>
          <div className={styles.inlineActions}><Link to="/producers">Clear filters</Link><button type="submit">Search producers</button></div>
        </div>
      </form>
      {invalid ? <div className={styles.emptyState}><p role="alert">Enter a valid producer name or ID for the selected search mode.</p></div>
        : producers.isPending ? <div className={styles.emptyState}><p role="status">Loading producers…</p></div>
        : producers.isError ? <div className={styles.emptyState}>
          <p role="alert">{producers.error instanceof ApiError ? producers.error.message : 'Unable to load producers.'}</p>
          <button type="button" onClick={() => { void producers.refetch() }}>Try again</button>
        </div> : producers.data.length === 0 ? <div className={styles.emptyState}><h3>No producers found</h3><p>{offset ? 'No more producers on this page.' : 'No producers match your search. Adjust the search or create a producer.'}</p></div>
        : <div className={styles.tableContainer}><table className={styles.jobsTable} aria-label="Registered producers">
          <thead><tr><th scope="col">Name</th><th scope="col">Owner</th><th scope="col">Credential status</th></tr></thead>
          <tbody>{producers.data.map((producer) => <tr key={producer.id} className={styles.jobRow}>
            <td data-label="Name"><Link className={styles.jobLink} to={`/producers/${producer.id}`}>{producer.name}</Link><span className={styles.recordId}>#{producer.id}</span></td>
            <td data-label="Owner">{producer.owner_username}{producer.user_id === user?.id ? ' (you)' : ''}</td>
            <td data-label="Credential status"><span className={styles.statusBadge} data-status={producer.active ? 'SUCCEEDED' : 'PENDING'}>{producer.active ? 'Active' : 'Inactive'}</span></td>
          </tr>)}</tbody>
        </table></div>}
      {!lookup && !invalid && producers.isSuccess && (offset > 0 || producers.data.length === limit) && <nav className={styles.pagination} aria-label="Producer pages">
        <span>Page {Math.floor(offset / limit) + 1}<span className={styles.pageSize}>{limit} per page</span></span>
        <div className={styles.inlineActions}>
          <button className={styles.controlButton} type="button" disabled={offset === 0 || producers.isFetching} onClick={() => changePage(Math.max(0, offset - limit))}>Previous producers</button>
          <button className={styles.controlButton} type="button" disabled={producers.data.length < limit || producers.isFetching} onClick={() => changePage(offset + limit)}>Next producers</button>
        </div>
      </nav>}
    </section>
  </>
}

function ProducerKey({ secret }: { secret: string }) {
  const [copyStatus, setCopyStatus] = useState('')
  async function copy() {
    try {
      await navigator.clipboard.writeText(secret)
      setCopyStatus('API key copied. Save it securely.')
    } catch {
      setCopyStatus('Unable to copy. Select the API key above and copy it manually.')
    }
  }
  return <section aria-label="New producer API key">
    <h3>API key</h3>
    <p>Save this API key now. It cannot be retrieved after leaving or reloading this page. Keep it in your application's private configuration and send it in the X-API-Key header.</p>
    <pre className={styles.json} aria-label="Producer API key">{secret}</pre>
    <div className={styles.actions}><button type="button" onClick={() => { void copy() }}>Copy API key</button></div>
    {copyStatus && <p role="status">{copyStatus}</p>}
  </section>
}

export function CreateProducerPage() {
  const { user, request } = useAuth()
  const queryClient = useQueryClient()
  const [created, setCreated] = useState<(Producer & { secret_api_key: string }) | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => { pending.current?.abort() }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current || created) return
    const name = String(new FormData(event.currentTarget).get('name') ?? '')
    if (!namePattern.test(name)) {
      setError(new ApiError('Choose a name of 3–16 letters, digits, underscores or hyphens.', null, [
        { loc: ['name'], msg: 'Use 3–16 letters, digits, underscores or hyphens.', type: 'value_error' },
      ]))
      return
    }
    const controller = new AbortController()
    pending.current = controller
    setSubmitting(true)
    setError(null)
    try {
      const producer = await request<Producer & { secret_api_key: string }>('/producers', { method: 'POST', json: { name }, signal: controller.signal })
      if (!Number.isSafeInteger(producer?.id) || producer.id <= 0 || producer.user_id !== user!.id || typeof producer.secret_api_key !== 'string' || !producer.secret_api_key) {
        throw new ApiError('Orqbit returned an invalid producer creation response.', null)
      }
      if (!controller.signal.aborted) {
        setCreated(producer)
        void queryClient.invalidateQueries({ queryKey: ['producers', user!.id] })
      }
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof ApiError ? cause : new ApiError('Unable to create this producer. Please try again.', null))
    } finally {
      if (!controller.signal.aborted) { pending.current = null; setSubmitting(false) }
    }
  }

  const nameError = error?.status === 409 ? 'This producer name is already taken. Choose a different name.'
    : error?.fieldErrors.filter(({ loc }) => loc.includes('name')).map(({ msg }) => msg).join(' ')
  return <>
    <div className={styles.pageHeading}><Link to="/producers">Back to Producers</Link><h1>Create a producer</h1></div>
    <section className={styles.placeholder} aria-label={created ? 'Producer created' : 'Producer creation'}>
      {created ? <>
        <h2>{created.name} created</h2>
        <ProducerKey secret={created.secret_api_key} />
        <div className={styles.actions}><Link to={`/producers/${created.id}`}>I've saved the key — view producer</Link></div>
      </> : <>
        {error && <div className={styles.formError} role="alert">{nameError || error.message}</div>}
        {error && error.fieldErrors.length === 0 && (error.status === null || error.status < 400 || error.status >= 500 || error.status === 408) && <p>The producer may have been created, but its key was not received. Check your producers before retrying; use reissue if you need a new key.</p>}
        <form onSubmit={submit} aria-label="Create a producer" aria-busy={submitting}>
          <fieldset className={styles.authFields} disabled={submitting}>
            <div><label htmlFor="producer-name">Producer name</label>
              <input id="producer-name" name="name" required minLength={3} maxLength={16} pattern="[a-zA-Z0-9_\-]{3,16}" autoComplete="off"
                aria-invalid={!!nameError} aria-describedby="producer-name-help producer-name-error" />
              <small id="producer-name-help">3–16 letters, digits, underscores or hyphens. Names must be unique.</small>
              <small id="producer-name-error">{nameError}</small>
            </div>
            <button type="submit">{submitting ? 'Creating…' : 'Create producer'}</button>
          </fieldset>
        </form>
      </>}
    </section>
  </>
}

const actions = {
  'api-key': { title: 'Reissue API key?', confirm: 'Confirm reissue', help: 'The old key will stop working immediately. Update your application with the new key. Reissuing does not reactivate an inactive producer.' },
  deactivate: { title: 'Deactivate producer?', confirm: 'Confirm deactivation', help: 'This producer will no longer be able to authenticate. Existing jobs are preserved. Reactivation is not currently available.' },
  delete: { title: 'Delete producer?', confirm: 'Confirm deletion', help: 'This permanently deletes the producer. Producers referenced by jobs cannot be deleted; deactivate them instead.' },
}
type ProducerAction = keyof typeof actions

export function ProducerDetailsPage() {
  const { producerId = '' } = useParams()
  // Changing the route discards any displayed key and cancels pending actions.
  return <ProducerDetails key={producerId} producerId={producerId} />
}

function ProducerDetails({ producerId }: { producerId: string }) {
  const { user, request } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [action, setAction] = useState<ProducerAction | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [secret, setSecret] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => { pending.current?.abort() }, [])
  const detailsKey = ['producer-details', user?.id, producerId]
  const details = useQuery({
    queryKey: detailsKey,
    enabled: !!user && validId(producerId),
    queryFn: ({ signal }) => request<Producer>(`/producers/${producerId}`, { signal }),
  })
  const producer = details.data
  const unavailable = !validId(producerId) || (details.error instanceof ApiError && [403, 404].includes(details.error.status ?? 0))

  async function confirm() {
    if (!action || pending.current || producer?.user_id !== user?.id) return
    const controller = new AbortController()
    pending.current = controller
    setBusy(true)
    setError(null)
    setNotice('')
    setSecret(null)
    try {
      if (action === 'api-key') {
        const result = await request<{ secret_api_key: string }>(`/producers/${producerId}/api-key`, { method: 'POST', signal: controller.signal })
        if (typeof result?.secret_api_key !== 'string' || !result.secret_api_key) throw new ApiError('Orqbit returned an invalid API key response.', null)
        if (!controller.signal.aborted) setSecret(result.secret_api_key)
      } else if (action === 'deactivate') {
        const updated = await request<Producer>(`/producers/${producerId}/deactivate`, { method: 'POST', signal: controller.signal })
        if (!controller.signal.aborted) {
          queryClient.setQueryData(detailsKey, updated)
          setNotice('Producer deactivated. Existing jobs are preserved.')
        }
      } else {
        await request<void>(`/producers/${producerId}`, { method: 'DELETE', signal: controller.signal })
      }
      if (!controller.signal.aborted) {
        void queryClient.invalidateQueries({ queryKey: ['producers', user!.id] })
        if (action === 'delete') {
          queryClient.removeQueries({ queryKey: detailsKey, exact: true })
          navigate('/producers', { replace: true })
        }
        setAction(null)
      }
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof ApiError ? cause : new ApiError('Unable to update this producer. Please try again.', null))
    } finally {
      if (!controller.signal.aborted) { pending.current = null; setBusy(false) }
    }
  }

  return <>
    <div className={styles.pageHeading}><Link to="/producers">Back to Producers</Link><h1>Producer details</h1></div>
    {unavailable ? <section className={styles.placeholder}><h2>Producer unavailable</h2><p>This producer could not be found or you do not have permission to view it.</p></section>
      : details.isError ? <section className={styles.placeholder}><p role="alert">{details.error instanceof ApiError ? details.error.message : 'Unable to load this producer.'}</p><button type="button" onClick={() => { void details.refetch() }}>Try again</button></section>
      : !producer ? <p role="status">Loading producer details…</p>
      : <section className={styles.placeholder} aria-label="Producer metadata">
        <h2>{producer.name}</h2>
        <dl className={styles.metadata}>
          <div><dt>Producer ID</dt><dd>#{producer.id}</dd></div>
          <div><dt>Owner</dt><dd>{producer.owner_username}{producer.user_id === user?.id ? ' (you)' : ''}</dd></div>
          <div><dt>Credential status</dt><dd>{producer.active ? 'Active' : 'Inactive'}</dd></div>
        </dl>
        {notice && <p role="status">{notice}</p>}
        {producer.user_id === user?.id && <>
          <div className={styles.actions}>
            {(['api-key', 'deactivate', 'delete'] as const).map((value) => <button type="button" key={value} disabled={busy || details.isFetching || (value === 'deactivate' && !producer.active)}
              onClick={() => { setAction(value); setError(null); setNotice('') }}>{value === 'api-key' ? 'Reissue API key' : value === 'deactivate' ? 'Deactivate producer' : 'Delete producer'}</button>)}
          </div>
          {error && <div className={styles.formError} role="alert">{error.status === 409 && action === 'delete' ? 'This producer is referenced by jobs and cannot be deleted. Deactivate it instead.' : error.message}</div>}
          {error && (error.status === null || error.status < 400 || error.status === 408 || error.status >= 500) && <p>The action may have succeeded. Refresh the producer details before retrying. {action === 'api-key' && 'The previous key may already be invalid; reissue again to obtain a usable key.'}</p>}
          {error && <button type="button" disabled={busy || details.isFetching} onClick={() => { void details.refetch() }}>Refresh producer details</button>}
          {action && <section aria-label="Confirm producer action" aria-busy={busy}>
            <h3>{actions[action].title}</h3><p>{actions[action].help}</p>
            <div className={styles.actions}>
              <button type="button" disabled={busy} onClick={() => { void confirm() }}>{busy ? 'Working…' : actions[action].confirm}</button>
              <button className={styles.controlButton} type="button" disabled={busy} onClick={() => { setAction(null); setError(null) }}>Cancel</button>
            </div>
          </section>}
          {secret && <ProducerKey key={secret} secret={secret} />}
        </>}
      </section>}
  </>
}
