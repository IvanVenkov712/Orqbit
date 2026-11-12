// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import App from '../App'
import {
  user, fetchMock, worker, response, fillLogin, enterApp, fillWorkerRegistration, mockApi, setupAppTests,
} from './app-test-utils'

setupAppTests()

test('opens an accessible worker belonging to another owner without exposing credentials', async () => {
  mockApi(async (path) => path === '/api/workers/17'
    ? response({ ...worker, user_id: 888, owner_username: 'other-owner', name: 'shared-worker', secret_api_key: 'never-show-key' }) : undefined)
  await enterApp('/workers/17')
  const details = await screen.findByRole('region', { name: 'Worker metadata' })
  expect(details.textContent).toContain('shared-worker')
  expect(details.textContent).toContain('other-owner')
  expect(details.textContent).not.toContain('User #888')
  expect(details.textContent).not.toContain('demo-user (you)')
  expect(details.textContent).not.toContain('never-show-key')
})

test('combines worker owner, type, registration status and creation filters before pagination', async () => {
  await enterApp('/workers?offset=20&view=shared')
  await screen.findByRole('table', { name: 'Registered workers' })
  const from = '2026-11-10T10:00:00'
  const before = '2026-11-11T10:00:00'
  fireEvent.change(screen.getByLabelText('Owner username'), { target: { value: 'other-owner' } })
  fireEvent.change(screen.getByLabelText('Supported job type'), { target: { value: 'sum & more' } })
  fireEvent.change(screen.getByLabelText('Credential/registration status'), { target: { value: 'false' } })
  fireEvent.change(screen.getByLabelText('Created from'), { target: { value: from } })
  fireEvent.change(screen.getByLabelText('Created before'), { target: { value: before } })
  fireEvent.submit(screen.getByRole('form', { name: 'Filter workers' }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([path]) => {
    const query = new URL(String(path), 'http://localhost').searchParams
    return query.get('owner_username') === 'other-owner' && !query.has('owner_id') && query.get('job_type') === 'sum & more'
      && query.get('active') === 'false' && query.get('offset') === '0'
      && query.get('created_from') === new Date(from).toISOString()
      && query.get('created_before') === new Date(before).toISOString()
  })).toBe(true))
  expect(new URLSearchParams(window.location.search).has('offset')).toBe(false)
  const filteredUrl = window.location.search
  await act(async () => { window.history.back() })
  await waitFor(() => expect((screen.getByLabelText('Owner username') as HTMLInputElement).value).toBe(''))
  await act(async () => { window.history.forward() })
  await waitFor(() => expect((screen.getByLabelText('Owner username') as HTMLInputElement).value).toBe('other-owner'))
  cleanup()
  render(<App />)
  await screen.findByRole('table', { name: 'Registered workers' })
  expect(window.location.search).toBe(filteredUrl)
  expect((screen.getByLabelText('Owner username') as HTMLInputElement).value).toBe('other-owner')
  expect((screen.getByLabelText('Credential/registration status') as HTMLSelectElement).value).toBe('false')
  fireEvent.click(screen.getByRole('link', { name: 'Clear filters' }))
  await waitFor(() => expect(window.location.search).toBe(''))
})

test('shows an empty list for an unknown owner username', async () => {
  mockApi(async (path) => String(path).startsWith('/api/workers?') ? response([]) : undefined)
  await enterApp('/workers?owner_username=missing-owner')
  await screen.findByText('No accessible workers match these filters.')
  expect((screen.getByLabelText('Owner username') as HTMLInputElement).value).toBe('missing-owner')
  expect(screen.queryByLabelText('Owner ID')).toBeNull()
  const query = new URL(String(fetchMock.mock.calls.find(([path]) => String(path).startsWith('/api/workers?'))![0]), 'http://localhost').searchParams
  expect(query.get('owner_username')).toBe('missing-owner')
  expect(query.has('owner_id')).toBe(false)
})

test('lists accessible workers across owners with metadata and no API keys', async () => {
  mockApi(async (path) => String(path).startsWith('/api/workers?')
    ? response([{ ...worker, secret_api_key: 'never-show-key', secret_api_key_hash: 'never-show-hash' }, { ...worker, id: 18, user_id: 99, owner_username: 'other-owner', name: 'shared-worker' }])
    : undefined)
  await enterApp('/workers')
  const table = await screen.findByRole('table', { name: 'Registered workers' })
  expect(table.textContent).toContain(user.username)
  expect(table.textContent).toContain('add_numbers, sum')
  expect(table.textContent).toContain('Credential/registration status')
  expect(table.textContent).toContain('Active')
  expect(table.textContent).toContain('Private')
  expect(table.textContent).toContain('other-owner')
  expect(table.textContent).not.toContain('User #99')
  expect(document.body.textContent).not.toMatch(/never-show-key|never-show-hash/)
  expect(screen.getByText(/does not establish that a worker process is online/)).toBeTruthy()
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/workers?limit=20&offset=0')).toBe(true)
  fireEvent.click(screen.getByRole('link', { name: worker.name }))
  const details = await screen.findByRole('region', { name: 'Worker metadata' })
  expect(details.textContent).toContain('#17')
  expect(details.textContent).toContain('demo-user (you)')
  expect(within(details).getAllByRole('listitem').map((item) => item.textContent)).toEqual(worker.supported_types)
  expect(screen.queryByRole('button', { name: 'Copy API key' })).toBeNull()
})

test.each([
  ['/workers', 'No accessible workers match these filters.'],
  ['/workers?job_type=unknown', 'No accessible workers match these filters.'],
  ['/workers?offset=20', 'No more workers on this page.'],
])('shows a useful empty worker state at %s', async (path, message) => {
  mockApi(async (path) => String(path).startsWith('/api/workers?') ? response([]) : undefined)
  await enterApp(path)
  expect(await screen.findByText(message)).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Register a worker' })).toBeTruthy()
  if (path.includes('offset')) {
    expect((screen.getByRole('button', { name: 'Previous workers' }) as HTMLButtonElement).disabled).toBe(false)
    expect((screen.getByRole('button', { name: 'Next workers' }) as HTMLButtonElement).disabled).toBe(true)
  }
})

test('preserves worker type filters, pages and unrelated parameters across navigation and reload', async () => {
  mockApi(async (path) => String(path).startsWith('/api/workers?')
    ? response(new URL(String(path), 'http://localhost').searchParams.get('offset') === '40' ? [] : Array.from({ length: 20 }, (_, i) => ({ ...worker, id: 100 + i, name: `worker-${i}` })))
    : undefined)
  await enterApp('/workers?job_type=add_numbers&offset=20&view=mine')
  await screen.findByRole('table', { name: 'Registered workers' })
  fireEvent.click(screen.getByRole('button', { name: 'Next workers' }))
  await screen.findByText('No more workers on this page.')
  expect(window.location.search).toBe('?job_type=add_numbers&offset=40&view=mine')
  fireEvent.click(screen.getByRole('button', { name: 'Previous workers' }))
  await screen.findByRole('table', { name: 'Registered workers' })
  expect(window.location.search).toBe('?job_type=add_numbers&offset=20&view=mine')
  fireEvent.change(screen.getByLabelText('Supported job type'), { target: { value: 'sum & more' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Filter workers' }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([path]) => path === '/api/workers?limit=20&offset=0&job_type=sum+%26+more')).toBe(true))
  expect(window.location.search).toBe('?job_type=sum+%26+more&view=mine')
  await act(async () => { window.history.back() })
  await waitFor(() => expect(window.location.search).toBe('?job_type=add_numbers&offset=20&view=mine'))
  expect((screen.getByLabelText('Supported job type') as HTMLInputElement).value).toBe('add_numbers')
  await act(async () => { window.history.forward() })
  await waitFor(() => expect((screen.getByLabelText('Supported job type') as HTMLInputElement).value).toBe('sum & more'))
  cleanup()
  render(<App />)
  await screen.findByRole('table', { name: 'Registered workers' })
  expect((screen.getByLabelText('Supported job type') as HTMLInputElement).value).toBe('sum & more')
  expect(window.location.search).toBe('?job_type=sum+%26+more&view=mine')
  fireEvent.change(screen.getByLabelText('Supported job type'), { target: { value: '' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Filter workers' }))
  expect(window.location.search).toBe('?view=mine')
})

test.each(['-1', 'invalid', '1.5', '9007199254740992'])('normalizes invalid worker offset %s before requesting', async (offset) => {
  await enterApp(`/workers?offset=${offset}`)
  await screen.findByRole('table', { name: 'Registered workers' })
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/workers?limit=20&offset=0')).toBe(true)
})

test.each(['/workers', '/workers/17'])('shows worker loading and failure states with manual retry at %s', async (route) => {
  let resolve!: (value: Response) => void
  let fail = true
  mockApi(async (path) => {
    if (String(path).startsWith('/api/workers') && fail) return new Promise((done) => { resolve = done })
  })
  await enterApp(route)
  expect(screen.getByRole('status').textContent).toMatch(/Loading worker/)
  await act(async () => { resolve(response({ detail: 'private server detail' }, 503)) })
  expect((await screen.findByRole('alert')).textContent).toContain('temporarily unavailable')
  fail = false
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  if (route === '/workers') await screen.findByRole('table', { name: 'Registered workers' })
  else await screen.findByRole('region', { name: 'Worker metadata' })
})

test.each(['not-a-number', '0', '-1', '9007199254740992'])('rejects invalid worker ID %s without fetching', async (id) => {
  await enterApp(`/workers/${id}`)
  expect(screen.getByRole('heading', { name: 'Worker unavailable' })).toBeTruthy()
  expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith('/api/workers'))).toBe(false)
})

test.each(['missing', 'inaccessible'])('hides worker details when %s', async (reason) => {
  mockApi(async (path) => path === '/api/workers/17'
    ? response({ detail: 'Worker not found' }, reason === 'missing' ? 404 : 403)
    : undefined)
  await enterApp('/workers/17')
  await screen.findByRole('heading', { name: 'Worker unavailable' })
  expect(screen.queryByRole('region', { name: 'Worker metadata' })).toBeNull()
  expect(document.body.textContent).not.toContain('hidden-worker')
})

test('shows inactive credentials and visibility grants without displaying unexpected secrets', async () => {
  mockApi(async (path) => path === '/api/workers/17'
    ? response({ ...worker, active: false, permission_policy: 'PERMITTED_USERS', permitted_user_ids: [12, 15], secret_api_key: 'never-show-key', secret_api_key_hash: 'never-show-hash' })
    : undefined)
  await enterApp('/workers/17')
  const details = await screen.findByRole('region', { name: 'Worker metadata' })
  expect(details.textContent).toContain('Inactive')
  expect(details.textContent).toContain('Permitted users')
  expect(details.textContent).toContain('12, 15')
  expect(details.textContent).not.toMatch(/never-show-key|never-show-hash/)
})

test('registers privately and shows the key once with explicit copy and save instructions', async () => {
  const secret = 'one-time-worker-key'
  mockApi(async (path, options) => path === '/api/workers' && options?.method === 'POST'
    ? response({ ...worker, secret_api_key: secret }) : undefined)
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  const setItem = vi.spyOn(Storage.prototype, 'setItem')
  await enterApp('/workers/new')
  expect((screen.getByLabelText('Visibility policy') as HTMLSelectElement).value).toBe('PRIVATE')
  fillWorkerRegistration()
  const key = await screen.findByLabelText('New worker API key')
  expect(key.textContent).toBe(secret)
  expect(screen.getByText(/cannot be retrieved after leaving or reloading/)).toBeTruthy()
  expect(screen.getByText(/API_KEY setting/)).toBeTruthy()
  const [, options] = fetchMock.mock.calls.find(([path, options]) => path === '/api/workers' && options?.method === 'POST')!
  expect(JSON.parse(String(options?.body))).toEqual({ name: worker.name, supported_types: ['add_numbers', 'sum'], permission_policy: 'PRIVATE' })
  expect(new Headers(options?.headers).get('Authorization')).toMatch(/^Bearer /)
  expect(writeText).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Copy API key' }))
  expect((await screen.findByRole('status')).textContent).toContain('API key copied')
  expect(writeText).toHaveBeenCalledExactlyOnceWith(secret)
  expect(localStorage.length).toBe(1)
  expect(sessionStorage.length).toBe(0)
  expect(setItem.mock.calls.some((args) => args.some((arg) => String(arg).includes(secret)))).toBe(false)
  expect(JSON.stringify(window.history.state)).not.toContain(secret)
  expect(window.location.href).not.toContain(secret)
  fireEvent.click(screen.getByRole('link', { name: /I've saved the key/ }))
  await screen.findByRole('region', { name: 'Worker metadata' })
  expect(document.body.textContent).not.toContain(secret)
  await act(async () => { window.history.back() })
  await screen.findByRole('form', { name: 'Register a worker' })
  expect(screen.queryByLabelText('New worker API key')).toBeNull()
})

test.each([
  ['PRIVATE', "Only you can view this worker's metadata."],
  ['PERMITTED_USERS', "You and the listed users can view this worker's metadata."],
  ['ALL', "Any authenticated user can view this worker's metadata."],
])('registers with %s visibility and submits only applicable grants', async (policy, help) => {
  await enterApp('/workers/new')
  expect(screen.getByLabelText('Visibility policy').querySelectorAll('option')).toHaveLength(3)
  fireEvent.change(screen.getByLabelText('Visibility policy'), { target: { value: 'PERMITTED_USERS' } })
  fireEvent.change(screen.getByLabelText('Permitted user IDs'), { target: { value: '12, 15 12' } })
  fireEvent.change(screen.getByLabelText('Visibility policy'), { target: { value: policy } })
  expect(!!screen.queryByLabelText('Permitted user IDs')).toBe(policy === 'PERMITTED_USERS')
  expect(screen.queryByLabelText('Permitted worker IDs')).toBeNull()
  const description = document.getElementById('worker-policy-help')!.textContent
  expect(description).toContain(`Worker metadata visibility: ${help}`)
  expect(description).toContain('does not reveal the API key or allow others to claim as this worker')
  expect(description).toContain('Job access policies determine which jobs it can claim.')
  fetchMock.mockResolvedValueOnce(response({ ...worker, secret_api_key: 'new-key' }))
  fillWorkerRegistration()
  await screen.findByLabelText('New worker API key')
  const [, options] = fetchMock.mock.calls.find(([path]) => path === '/api/workers')!
  expect(JSON.parse(String(options?.body))).toEqual({
    name: worker.name, supported_types: ['add_numbers', 'sum'], permission_policy: policy,
    ...(policy === 'PERMITTED_USERS' ? { permitted_user_ids: [12, 15] } : {}),
  })
})

test('discards the new key on reload and does not repeat registration', async () => {
  mockApi(async (path) => path === '/api/workers'
    ? response({ ...worker, secret_api_key: 'discard-on-reload' }) : undefined)
  await enterApp('/workers/new')
  fillWorkerRegistration()
  await screen.findByLabelText('New worker API key')
  cleanup()
  render(<App />)
  await screen.findByRole('form', { name: 'Register a worker' })
  expect(document.body.textContent).not.toContain('discard-on-reload')
  expect(fetchMock.mock.calls.filter(([path]) => path === '/api/workers')).toHaveLength(1)
})

test('offers manual key copying when clipboard access fails', async () => {
  mockApi(async (path) => path === '/api/workers'
    ? response({ ...worker, secret_api_key: 'manual-copy-key' }) : undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('Clipboard denied')) } })
  await enterApp('/workers/new')
  fillWorkerRegistration()
  await screen.findByLabelText('New worker API key')
  fireEvent.click(screen.getByRole('button', { name: 'Copy API key' }))
  expect((await screen.findByRole('status')).textContent).toContain('copy it manually')
  expect(screen.getByLabelText('New worker API key').textContent).toBe('manual-copy-key')
})

test('makes duplicate worker names actionable and allows correcting the name', async () => {
  mockApi(async (path, options) => path === '/api/workers'
    ? JSON.parse(String(options?.body)).name === worker.name
      ? response({ detail: 'Worker name already exists' }, 409)
      : response({ ...worker, name: 'another-worker', secret_api_key: 'new-key' })
    : undefined)
  await enterApp('/workers/new')
  fillWorkerRegistration()
  expect((await screen.findByRole('alert')).textContent).toContain('Choose a different name')
  expect(screen.getByLabelText('Worker name').getAttribute('aria-invalid')).toBe('true')
  expect((screen.getByLabelText('Supported types') as HTMLTextAreaElement).value).toContain('sum')
  fireEvent.change(screen.getByLabelText('Worker name'), { target: { value: 'another-worker' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Register a worker' }))
  expect(await screen.findByRole('heading', { name: 'another-worker registered' })).toBeTruthy()
})

test.each(['', '  ', 'add_numbers\n', 'a'.repeat(101)])('rejects invalid supported types %j before registration', async (types) => {
  await enterApp('/workers/new')
  fillWorkerRegistration(types)
  expect(screen.getByRole('alert').textContent).toContain('one non-blank supported type per line')
  expect(screen.queryByText(/registration may have succeeded/)).toBeNull()
  expect(screen.getByLabelText('Supported types').getAttribute('aria-invalid')).toBe('true')
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/workers')).toBe(false)
})

test('shows backend worker field validation errors inline', async () => {
  mockApi(async (path) => path === '/api/workers'
    ? response({ detail: [{ loc: ['body', 'supported_types', 0], msg: 'Unsupported value', type: 'value_error' }] }, 422)
    : undefined)
  await enterApp('/workers/new')
  fillWorkerRegistration()
  expect((await screen.findByRole('alert')).textContent).toContain('Unsupported value')
  expect(screen.getByLabelText('Supported types').getAttribute('aria-invalid')).toBe('true')
  expect(document.getElementById('worker-types-error')?.textContent).toBe('Unsupported value')
  expect(screen.queryByText(/registration may have succeeded/)).toBeNull()
})

test('explains an uncertain registration without automatically retrying', async () => {
  mockApi(async (path) => {
    if (path === '/api/workers') throw new Error('private diagnostics')
  })
  await enterApp('/workers/new')
  fillWorkerRegistration()
  expect((await screen.findByRole('alert')).textContent).toContain('Unable to reach Orqbit')
  expect(screen.getByText(/registration may have succeeded/)).toBeTruthy()
  expect(fetchMock.mock.calls.filter(([path]) => path === '/api/workers')).toHaveLength(1)
})

test.each(['navigate', 'logout'])('prevents duplicate worker registration and cancels on %s', async (action) => {
  let resolve!: (value: Response) => void
  mockApi(async (path) => path === '/api/workers'
    ? new Promise((done) => { resolve = done }) : undefined)
  await enterApp('/workers/new')
  fillWorkerRegistration()
  expect((screen.getByRole('button', { name: 'Registering…' }) as HTMLButtonElement).matches(':disabled')).toBe(true)
  fireEvent.submit(screen.getByRole('form', { name: 'Register a worker' }))
  expect(fetchMock.mock.calls.filter(([path]) => path === '/api/workers')).toHaveLength(1)
  const signal = fetchMock.mock.calls.find(([path]) => path === '/api/workers')![1]?.signal
  if (action === 'navigate') fireEvent.click(screen.getByRole('link', { name: 'Back to Workers' }))
  else fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(signal?.aborted).toBe(true)
  await act(async () => { resolve(response({ ...worker, secret_api_key: 'late-secret' })) })
  expect(document.body.textContent).not.toContain('late-secret')
  expect(screen.queryByLabelText('New worker API key')).toBeNull()
})

test('refreshes the owned worker list after registration', async () => {
  let registered = false
  mockApi(async (path) => {
    if (path === '/api/workers') {
      registered = true
      return response({ ...worker, secret_api_key: 'new-key' })
    }
    if (String(path).startsWith('/api/workers?')) return response(registered ? [worker] : [])
  })
  await enterApp('/workers')
  await screen.findByText('No accessible workers match these filters.')
  fireEvent.click(screen.getByRole('link', { name: 'Register a worker' }))
  fillWorkerRegistration()
  await screen.findByLabelText('New worker API key')
  fireEvent.click(screen.getByRole('link', { name: 'Back to Workers' }))
  await screen.findByRole('link', { name: worker.name })
  expect(screen.queryByLabelText('New worker API key')).toBeNull()
})

test('discards worker records across accounts', async () => {
  await enterApp('/workers/17')
  await screen.findByRole('region', { name: 'Worker metadata' })
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  await screen.findByRole('heading', { name: 'Sign in' })
  mockApi(async (path) => path === '/api/users/me/' ? response({ ...user, id: 888 })
    : path === '/api/workers/17' ? response({ detail: 'Worker not found' }, 404) : undefined)
  fillLogin()
  await screen.findByRole('heading', { name: 'Worker unavailable' })
  expect(screen.queryByRole('region', { name: 'Worker metadata' })).toBeNull()
})
