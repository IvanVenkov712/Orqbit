// @vitest-environment jsdom
import { act, fireEvent, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import {
  fetchMock, storageKey, worker, response, enterApp, fillJob, submitJob, fillWorkerRegistration, mockApi, setupAppTests,
} from './app-test-utils'

setupAppTests()

test.each(['', 'NaN', 'Infinity', '1e309', '0x10', '2oops'])('rejects an invalid number "%s" before making a request', async (value) => {
  await enterApp('/jobs/new')
  fillJob({ amount: 1 })
  fireEvent.change(screen.getByLabelText('Value for Parameters 1'), { target: { value } })
  submitJob()
  expect(screen.getByRole('alert').textContent).toContain('Parameters.amount: enter a finite number')
  expect(screen.getByRole('group', { name: 'Parameters' }).getAttribute('aria-invalid')).toBe('true')
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(window.location.pathname).toBe('/jobs/new')
})

test.each(['', '   '])('rejects a blank parameter name "%s"', async (name) => {
  await enterApp('/jobs/new')
  fillJob({ [name]: 'value' })
  submitJob()
  expect(screen.getByRole('alert').textContent).toContain('each parameter needs a name')
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test.each([false, true])('rejects duplicate names within an object (nested: %s)', async (nested) => {
  await enterApp('/jobs/new')
  fillJob(nested ? { options: { count: 1, other: 2 } } : { count: 1, other: 2 })
  fireEvent.change(screen.getByLabelText(`Name for ${nested ? 'Parameters 1 fields 2' : 'Parameters 2'}`), { target: { value: 'count' } })
  submitJob()
  expect(screen.getByRole('alert').textContent).toContain('duplicate parameter name "count"')
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test.each(['   ', 'a'.repeat(101)])('rejects an invalid job type before making a request', async (jobType) => {
  await enterApp('/jobs/new')
  fillJob({}, jobType)
  submitJob()
  expect(screen.getByRole('alert').textContent).toContain('job type')
  expect(screen.getByLabelText('Job type').getAttribute('aria-invalid')).toBe('true')
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test('submits a private job with bearer authentication and a key, preserving type and nested parameters', async () => {
  await enterApp('/jobs/new')
  expect((screen.getByLabelText('Access policy') as HTMLSelectElement).value).toBe('PRIVATE')
  expect(screen.getByLabelText('Access policy').querySelectorAll('option')).toHaveLength(5)
  fillJob({ nested: { enabled: true, values: [1, null, 'two'] } }, ' custom_type ')
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  fireEvent.click(screen.getByRole('button', { name: 'Submit job' }))
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  expect(window.location.pathname).toBe('/jobs/42')
  const [path, options] = fetchMock.mock.calls[2]
  expect(path).toBe('/api/jobs/')
  expect(options?.method).toBe('POST')
  expect(new Headers(options?.headers).get('Authorization')).toMatch(/^Bearer /)
  expect(new Headers(options?.headers).get('Content-Type')).toBe('application/json')
  expect(new Headers(options?.headers).get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/)
  expect(JSON.parse(String(options?.body))).toEqual({
    job_type: ' custom_type ', params: { nested: { enabled: true, values: [1, null, 'two'] } }, permission_policy: 'PRIVATE',
  })
  expect(localStorage.length).toBe(1)
  expect(sessionStorage.length).toBe(0)
})

test.each([
  ['PRIVATE', false, false, 'Only you can read this job.', 'Only your workers can claim it.'],
  ['PERMITTED_USERS', true, false, 'You and the listed users can read this job.', 'workers owned by the listed users can claim it.'],
  ['PERMITTED_WORKERS', false, true, 'does not give its owner read access.', 'Your workers and the listed workers can claim it.'],
  ['PERMITTED_WORKERS_AND_USERS', true, true, 'A worker grant alone does not give its owner read access.', 'the listed workers, and workers owned by the listed users can claim it.'],
  ['ALL', false, false, 'Any authenticated user can read this job.', 'Any authenticated worker can claim it.'],
] as const)('submits only applicable job grants for %s after switching policies', async (policy, users, workers, readHelp, claimHelp) => {
  await enterApp('/jobs/new')
  fillJob({})
  fireEvent.change(screen.getByLabelText('Access policy'), { target: { value: 'PERMITTED_WORKERS_AND_USERS' } })
  fireEvent.change(screen.getByLabelText('Permitted user IDs'), { target: { value: '12, 15 12' } })
  fireEvent.change(screen.getByLabelText('Permitted worker IDs'), { target: { value: '17 18,17' } })
  fireEvent.change(screen.getByLabelText('Access policy'), { target: { value: policy } })
  expect(!!screen.queryByLabelText('Permitted user IDs')).toBe(users)
  expect(!!screen.queryByLabelText('Permitted worker IDs')).toBe(workers)
  const help = document.getElementById('job-policy-help')!.textContent
  expect(help).toContain('User read access:')
  expect(help).toContain(readHelp)
  expect(help).toContain(claimHelp)
  expect(help).toContain('Worker claim access:')
  expect(help).toContain('a pending job and a matching supported job type')
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  submitJob()
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  const [, options] = fetchMock.mock.calls.find(([path]) => path === '/api/jobs/')!
  expect(JSON.parse(String(options?.body))).toEqual({
    job_type: 'add_numbers', params: {}, permission_policy: policy,
    ...(users ? { permitted_user_ids: [12, 15] } : {}),
    ...(workers ? { permitted_worker_ids: [17, 18] } : {}),
  })
  // The read response has no policy or grants; details must not infer a policy.
  expect(screen.queryByLabelText('Access policy')).toBeNull()
})

test.each(['job users', 'job workers', 'worker users'])('validates positive IDs for %s and allows correcting them', async (target) => {
  const registering = target === 'worker users'
  await enterApp(registering ? '/workers/new' : '/jobs/new')
  if (!registering) fillJob({})
  fireEvent.change(screen.getByLabelText(registering ? 'Visibility policy' : 'Access policy'), {
    target: { value: target === 'job workers' ? 'PERMITTED_WORKERS' : 'PERMITTED_USERS' },
  })
  const ids = screen.getByLabelText(target === 'job workers' ? 'Permitted worker IDs' : 'Permitted user IDs')
  for (const value of ['0', '-1', '1.5', '1e3', '0x10', 'NaN', 'Infinity', '12, bad', '9007199254740992']) {
    fireEvent.change(ids, { target: { value } })
    if (registering) fillWorkerRegistration()
    else submitJob()
    expect(screen.getByRole('alert').textContent).toContain('positive whole-number IDs')
    expect(ids.getAttribute('aria-invalid')).toBe('true')
    expect(fetchMock.mock.calls.some(([path]) => path === (registering ? '/api/workers' : '/api/jobs/'))).toBe(false)
  }
  fireEvent.change(ids, { target: { value: '12, 15' } })
  mockApi(async (path) => path === (registering ? '/api/workers' : '/api/jobs/')
    ? response(registering ? { ...worker, secret_api_key: 'new-key' } : { id: 42 }) : undefined)
  if (registering) fillWorkerRegistration()
  else submitJob()
  await screen.findByRole('heading', { name: registering ? `${worker.name} registered` : 'Job details' })
})

test.each([
  ['jobs', 'PERMITTED_USERS', 'Permitted user IDs', 'permitted_user_ids', 'Some permitted users do not exist'],
  ['jobs', 'PERMITTED_WORKERS', 'Permitted worker IDs', 'permitted_worker_ids', 'Some permitted workers do not exist'],
  ['workers', 'PERMITTED_USERS', 'Permitted user IDs', 'permitted_user_ids', 'Some permitted users do not exist'],
])('surfaces missing records for %s %s and allows a corrected request', async (resource, policy, label, field, message) => {
  const registering = resource === 'workers'
  await enterApp(`/${resource}/new`)
  if (!registering) fillJob({})
  fireEvent.change(screen.getByLabelText(registering ? 'Visibility policy' : 'Access policy'), { target: { value: policy } })
  fireEvent.change(screen.getByLabelText(label), { target: { value: '99999' } })
  mockApi(async (path) => path === (registering ? '/api/workers' : '/api/jobs/')
    ? response({ detail: message }, 422) : undefined)
  if (registering) fillWorkerRegistration()
  else submitJob()
  expect((await screen.findByRole('alert')).textContent).toBe(message)
  expect((screen.getByLabelText(label) as HTMLInputElement).value).toBe('99999')
  expect(screen.queryByText(/may have succeeded|may already have been created/)).toBeNull()
  if (!registering) fireEvent.click(screen.getByRole('button', { name: 'Start a new submission' }))
  fireEvent.change(screen.getByLabelText(label), { target: { value: '12' } })
  mockApi(async (path) => path === (registering ? '/api/workers' : '/api/jobs/')
    ? response(registering ? { ...worker, secret_api_key: 'new-key' } : { id: 42 }) : undefined)
  if (registering) fillWorkerRegistration()
  else submitJob()
  await screen.findByRole('heading', { name: registering ? `${worker.name} registered` : 'Job details' })
  const calls = fetchMock.mock.calls.filter(([path]) => path === (registering ? '/api/workers' : '/api/jobs/'))
  expect(JSON.parse(String(calls[1][1]?.body))[field]).toEqual([12])
  if (!registering) expect(new Headers(calls[1][1]?.headers).get('Idempotency-Key')).not.toBe(new Headers(calls[0][1]?.headers).get('Idempotency-Key'))
})

test.each(['jobs', 'workers'])('shows backend grant validation errors beside %s ID inputs', async (resource) => {
  const registering = resource === 'workers'
  await enterApp(`/${resource}/new`)
  if (!registering) fillJob({})
  fireEvent.change(screen.getByLabelText(registering ? 'Visibility policy' : 'Access policy'), { target: { value: 'PERMITTED_USERS' } })
  fireEvent.change(screen.getByLabelText('Permitted user IDs'), { target: { value: '12' } })
  mockApi(async (path) => path === (registering ? '/api/workers' : '/api/jobs/')
    ? response({ detail: [{ loc: ['body', 'permitted_user_ids', 0], msg: 'Invalid user ID', type: 'value_error' }] }, 422) : undefined)
  if (registering) fillWorkerRegistration()
  else submitJob()
  expect((await screen.findByRole('alert')).textContent).toContain('Invalid user ID')
  expect(screen.getByLabelText('Permitted user IDs').getAttribute('aria-invalid')).toBe('true')
  expect(document.getElementById(registering ? 'worker-user-ids-error' : 'job-user-ids-error')?.textContent).toBe('Invalid user ID')
})

test('retries a shared job with its original grants and key', async () => {
  await enterApp('/jobs/new')
  fillJob({})
  fireEvent.change(screen.getByLabelText('Access policy'), { target: { value: 'PERMITTED_WORKERS_AND_USERS' } })
  fireEvent.change(screen.getByLabelText('Permitted user IDs'), { target: { value: '12' } })
  fireEvent.change(screen.getByLabelText('Permitted worker IDs'), { target: { value: '17' } })
  fetchMock.mockRejectedValueOnce(new TypeError('Connection lost'))
  submitJob()
  await screen.findByRole('alert')
  for (const label of ['Access policy', 'Permitted user IDs', 'Permitted worker IDs']) {
    expect(screen.getByLabelText(label).matches(':disabled')).toBe(true)
  }
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  fireEvent.click(screen.getByRole('button', { name: 'Retry submission' }))
  await screen.findByRole('heading', { name: 'Job details' })
  const calls = fetchMock.mock.calls.filter(([path]) => path === '/api/jobs/')
  expect(calls).toHaveLength(2)
  expect(calls[1][1]?.body).toBe(calls[0][1]?.body)
  expect(new Headers(calls[1][1]?.headers).get('Idempotency-Key')).toBe(new Headers(calls[0][1]?.headers).get('Idempotency-Key'))
  expect(JSON.parse(String(calls[1][1]?.body))).toMatchObject({ permitted_user_ids: [12], permitted_worker_ids: [17] })
})

test.each(['jobs', 'workers'])('accepts empty applicable grants for %s', async (resource) => {
  const registering = resource === 'workers'
  await enterApp(`/${resource}/new`)
  if (!registering) fillJob({})
  fireEvent.change(screen.getByLabelText(registering ? 'Visibility policy' : 'Access policy'), {
    target: { value: registering ? 'PERMITTED_USERS' : 'PERMITTED_WORKERS_AND_USERS' },
  })
  mockApi(async (path) => path === (registering ? '/api/workers' : '/api/jobs/')
    ? response(registering ? { ...worker, secret_api_key: 'new-key' } : { id: 42 }) : undefined)
  if (registering) fillWorkerRegistration()
  else submitJob()
  await screen.findByRole('heading', { name: registering ? `${worker.name} registered` : 'Job details' })
  const [, options] = fetchMock.mock.calls.find(([path]) => path === (registering ? '/api/workers' : '/api/jobs/'))!
  const payload = JSON.parse(String(options?.body))
  expect(payload.permitted_user_ids).toEqual([])
  if (!registering) expect(payload.permitted_worker_ids).toEqual([])
})

test('submits all value types, preserving text and names, mixed lists, and empty containers', async () => {
  await enterApp('/jobs/new')
  const params = {
    ' exact name ': '123', text: 'false\n"quoted"', emptyText: '', decimal: -1.25, zero: 0,
    enabled: true, disabled: false, absent: null, emptyObject: {}, emptyList: [],
    mixed: [{ same: false }, { same: true }, [1, 'two', null], []],
  }
  fillJob(params)
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  submitJob()
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body)).params).toEqual(params)
})

test('an empty editor submits an empty object', async () => {
  await enterApp('/jobs/new')
  fillJob({})
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  submitJob()
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body)).params).toEqual({})
})

test('removing parameters, nested fields, and list items preserves the remaining values and order', async () => {
  await enterApp('/jobs/new')
  fillJob({ options: { remove: 'gone', keep: 'kept' }, numbers: [2, 3, 5], remove: true })
  fireEvent.click(screen.getByRole('button', { name: 'Remove Parameters 1 fields 1' }))
  fireEvent.click(screen.getByRole('button', { name: 'Remove Parameters 2 items 2' }))
  fireEvent.click(screen.getByRole('button', { name: 'Remove Parameters 3' }))
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  submitJob()
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body)).params).toEqual({ options: { keep: 'kept' }, numbers: [2, 5] })
})

test('changing a type clears incompatible values and child fields', async () => {
  await enterApp('/jobs/new')
  fillJob({ value: { old: 'discard' } })
  fireEvent.change(screen.getByLabelText('Type for Parameters 1'), { target: { value: 'boolean' } })
  expect(screen.queryByLabelText('Name for Parameters 1 fields 1')).toBeNull()
  expect((screen.getByLabelText('Value for Parameters 1') as HTMLSelectElement).value).toBe('false')
  fireEvent.change(screen.getByLabelText('Type for Parameters 1'), { target: { value: 'text' } })
  expect((screen.getByLabelText('Value for Parameters 1') as HTMLTextAreaElement).value).toBe('')
  fireEvent.change(screen.getByLabelText('Value for Parameters 1'), { target: { value: 'new text' } })
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  submitJob()
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body)).params).toEqual({ value: 'new text' })
})

test('parameter names such as __proto__ are submitted as ordinary object properties', async () => {
  await enterApp('/jobs/new')
  const params = JSON.parse('{"__proto__":{"value":3},"constructor":"text"}')
  fillJob(params)
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  submitJob()
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body)).params).toEqual(params)
})

test('correcting a parameter error allows submission without discarding the draft', async () => {
  await enterApp('/jobs/new')
  fillJob({ count: 1 })
  fireEvent.change(screen.getByLabelText('Value for Parameters 1'), { target: { value: 'invalid' } })
  submitJob()
  expect(screen.getByRole('alert')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Value for Parameters 1'), { target: { value: '2e3' } })
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  submitJob()
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body)).params).toEqual({ count: 2000 })
})

test('retries an uncertain submission repeatedly with its original key and payload', async () => {
  await enterApp('/jobs/new')
  fillJob()
  fetchMock.mockRejectedValueOnce(new TypeError('private connection details'))
  submitJob()
  expect((await screen.findByRole('alert')).textContent).toContain('Unable to reach Orqbit')
  expect(screen.getByRole('status').textContent).toContain('may already have been created')
  expect(screen.getByRole('status').textContent).toContain('could create another job')
  expect((screen.getByLabelText('Job type') as HTMLInputElement).matches(':disabled')).toBe(true)
  for (const name of ['Name for Parameters 1', 'Type for Parameters 1', 'Value for Parameters 1 items 1']) {
    expect((screen.getByLabelText(name) as HTMLInputElement).matches(':disabled')).toBe(true)
  }
  expect(screen.getByRole('button', { name: 'Add parameter to Parameters' }).matches(':disabled')).toBe(true)
  expect(screen.getByRole('button', { name: 'Remove Parameters 1' }).matches(':disabled')).toBe(true)
  expect(document.body.textContent).not.toContain('private connection details')
  fetchMock.mockRejectedValueOnce(new TypeError('second lost response'))
  fireEvent.click(screen.getByRole('button', { name: 'Retry submission' }))
  await screen.findByRole('alert')
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  fireEvent.click(screen.getByRole('button', { name: 'Retry submission' }))
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  const retries = fetchMock.mock.calls.slice(3).filter(([path]) => path === '/api/jobs/')
  for (const call of retries) {
    expect(call[1]?.body).toBe(fetchMock.mock.calls[2][1]?.body)
    expect(new Headers(call[1]?.headers).get('Idempotency-Key')).toBe(new Headers(fetchMock.mock.calls[2][1]?.headers).get('Idempotency-Key'))
  }
  expect(retries).toHaveLength(2)
  expect(window.location.pathname).toBe('/jobs/42')
})

test.each([
  ['server failure', () => response({ detail: 'private server details' }, 503)],
  ['malformed response', () => new Response('not-json', { status: 200 })],
  ['empty response', () => new Response(null, { status: 200 })],
  ['missing job ID', () => response({ status: 'PENDING' })],
])('retains submission identity after a %s', async (_description, failedResponse) => {
  await enterApp('/jobs/new')
  fillJob()
  fetchMock.mockResolvedValueOnce(failedResponse())
  submitJob()
  await screen.findByRole('alert')
  expect(window.location.pathname).toBe('/jobs/new')
  expect(screen.getByRole('status').textContent).toContain('may already have been created')
  expect(document.body.textContent).not.toContain('private server details')
  fetchMock.mockResolvedValueOnce(response({ id: 42 }))
  fireEvent.click(screen.getByRole('button', { name: 'Retry submission' }))
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  expect(fetchMock.mock.calls[3][1]?.body).toBe(fetchMock.mock.calls[2][1]?.body)
  expect(new Headers(fetchMock.mock.calls[3][1]?.headers).get('Idempotency-Key')).toBe(new Headers(fetchMock.mock.calls[2][1]?.headers).get('Idempotency-Key'))
})

test('shows backend validation and uses a new key when a rejected request is edited', async () => {
  await enterApp('/jobs/new')
  fillJob()
  fetchMock.mockResolvedValueOnce(response({ detail: [
    { loc: ['body', 'params', 'numbers'], msg: 'Invalid numbers', type: 'value_error', input: 'private-rejected-value' },
    { loc: ['body', 'job_type'], msg: 'Invalid job type', type: 'value_error' },
  ] }, 422))
  submitJob()
  expect((await screen.findByRole('alert')).textContent).toContain('params.numbers: Invalid numbers')
  expect(document.getElementById('job-params-error')?.textContent).toBe('Invalid numbers')
  expect(document.getElementById('job-type-error')?.textContent).toBe('Invalid job type')
  expect(screen.getByLabelText('Job type').getAttribute('aria-invalid')).toBe('true')
  expect(screen.getByRole('group', { name: 'Parameters' }).getAttribute('aria-invalid')).toBe('true')
  expect(document.body.textContent).not.toContain('private-rejected-value')
  fireEvent.click(screen.getByRole('button', { name: 'Start a new submission' }))
  expect(screen.queryByRole('alert')).toBeNull()
  expect((screen.getByLabelText('Job type') as HTMLInputElement).matches(':disabled')).toBe(false)
  expect((screen.getByLabelText('Name for Parameters 1') as HTMLInputElement).value).toBe('numbers')
  expect((screen.getByLabelText('Value for Parameters 1 items 1') as HTMLInputElement).value).toBe('2')
  fillJob({ numbers: [4, 6] }, 'another_type')
  fetchMock.mockResolvedValueOnce(response({ id: 43 }))
  submitJob()
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  expect(new Headers(fetchMock.mock.calls[3][1]?.headers).get('Idempotency-Key')).not.toBe(new Headers(fetchMock.mock.calls[2][1]?.headers).get('Idempotency-Key'))
  expect(JSON.parse(String(fetchMock.mock.calls[3][1]?.body))).toEqual({ job_type: 'another_type', params: { numbers: [4, 6] }, permission_policy: 'PRIVATE' })
})

test('an explicit new submission gets a new key even when its payload is unchanged', async () => {
  await enterApp('/jobs/new')
  fillJob()
  fetchMock.mockResolvedValueOnce(response({ detail: 'Conflicting create requests' }, 409))
  submitJob()
  expect((await screen.findByRole('alert')).textContent).toBe('Conflicting create requests')
  fireEvent.click(screen.getByRole('button', { name: 'Start a new submission' }))
  fetchMock.mockResolvedValueOnce(response({ id: 43 }))
  submitJob()
  await screen.findByRole('heading', { level: 1, name: 'Job details' })
  expect(fetchMock.mock.calls[3][1]?.body).toBe(fetchMock.mock.calls[2][1]?.body)
  expect(new Headers(fetchMock.mock.calls[3][1]?.headers).get('Idempotency-Key')).not.toBe(new Headers(fetchMock.mock.calls[2][1]?.headers).get('Idempotency-Key'))
})

test('prevents duplicate in-flight submissions and ignores a late response after leaving the form', async () => {
  await enterApp('/jobs/new')
  fillJob()
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  submitJob()
  expect((screen.getByRole('button', { name: 'Submitting…' }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: 'Start a new submission' }) as HTMLButtonElement).disabled).toBe(true)
  submitJob()
  expect(fetchMock).toHaveBeenCalledTimes(3)
  const signal = fetchMock.mock.calls[2][1]?.signal
  fireEvent.click(screen.getByRole('link', { name: 'Back to Jobs' }))
  expect(signal?.aborted).toBe(true)
  await act(async () => { resolve(response({ id: 42 })) })
  expect(window.location.pathname).toBe('/jobs')
})

test('a rejected job credential ends the session and returns to login', async () => {
  await enterApp('/jobs/new')
  fillJob()
  fetchMock.mockResolvedValueOnce(response({ detail: 'Could not validate credentials' }, 401))
  submitJob()
  await screen.findByRole('heading', { level: 1, name: 'Sign in' })
  expect(localStorage.getItem(storageKey)).toBeNull()
  expect(screen.queryByRole('form', { name: 'Submit a job' })).toBeNull()
})
