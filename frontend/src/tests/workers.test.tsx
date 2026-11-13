// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import App from '../App'
import {
  user, fetchMock, worker, response, fillLogin, enterApp, fillWorkerRegistration, selectPermittedUser, mockApi, setupAppTests,
} from './app-test-utils'

setupAppTests()

test('sorts all workers through the API and groups credential status on the current page', async () => {
  mockApi(async (path) => String(path).startsWith('/api/workers?') ? response([
    worker, { ...worker, id: 18, name: 'inactive-worker', active: false },
  ]) : undefined)
  await enterApp('/workers?offset=20&view=shared')
  await screen.findByRole('table', { name: 'Registered workers' })
  fireEvent.click(screen.getByRole('button', { name: 'Name' }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([path]) => String(path) === '/api/workers?limit=20&offset=0&sort=name_asc')).toBe(true))
  expect(new URLSearchParams(window.location.search).get('view')).toBe('shared')
  expect(screen.getByRole('columnheader', { name: 'Name' }).getAttribute('aria-sort')).toBe('ascending')
  fireEvent.change(screen.getByLabelText('Group workers'), { target: { value: 'active' } })
  const inactive = screen.getByRole('rowgroup', { name: 'Inactive credentials group' })
  fireEvent.click(within(inactive).getByRole('button'))
  expect(screen.queryByRole('link', { name: 'inactive-worker' })).toBeNull()
  expect(screen.getByRole('link', { name: worker.name })).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Sort workers'), { target: { value: 'owner_desc' } })
  expect(new URLSearchParams(window.location.search).get('group')).toBe('active')
})

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
  expect(screen.queryByRole('link', { name: 'Edit worker' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Reissue API key' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Delete worker' })).toBeNull()
})

test('combines worker owner, type, registration status and creation filters before pagination', async () => {
  await enterApp('/workers?offset=20&view=shared')
  await screen.findByRole('table', { name: 'Registered workers' })
  const from = '2026-11-10T10:00:00'
  const before = '2026-11-11T10:00:00'
  fireEvent.click(screen.getByRole('button', { name: 'Filters' }))
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
  await waitFor(() => expect(window.location.search).toBe('?view=shared'))
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
  fireEvent.click(screen.getByRole('button', { name: /^Filters/ }))
  fireEvent.change(screen.getByLabelText('Supported job type'), { target: { value: 'sum & more' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Filter workers' }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([path]) => path === '/api/workers?limit=20&offset=0&job_type=sum+%26+more')).toBe(true))
  expect(window.location.search).toBe('?job_type=sum+%26+more&view=mine')
  await act(async () => { window.history.back() })
  await waitFor(() => {
    expect(window.location.search).toBe('?job_type=add_numbers&offset=20&view=mine')
    expect((screen.getByLabelText('Supported job type') as HTMLInputElement).value).toBe('add_numbers')
  })
  await act(async () => { window.history.forward() })
  await waitFor(() => expect((screen.getByLabelText('Supported job type') as HTMLInputElement).value).toBe('sum & more'))
  cleanup()
  render(<App />)
  await screen.findByRole('table', { name: 'Registered workers' })
  expect((screen.getByLabelText('Supported job type') as HTMLInputElement).value).toBe('sum & more')
  expect(window.location.search).toBe('?job_type=sum+%26+more&view=mine')
  fireEvent.click(screen.getByRole('button', { name: /^Filters/ }))
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
  await waitFor(() => expect(resolve).toBeTypeOf('function'))
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
  await waitFor(() => expect(details.textContent).toContain('alex, maria'))
  expect(details.textContent).not.toContain('12, 15')
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
  await selectPermittedUser('alex')
  await selectPermittedUser('maria')
  fireEvent.change(screen.getByLabelText('Visibility policy'), { target: { value: policy } })
  expect((screen.getByLabelText('Permitted users') as HTMLInputElement).disabled).toBe(policy !== 'PERMITTED_USERS')
  expect(screen.queryByLabelText('Permitted worker IDs')).toBeNull()
  const description = document.getElementById('worker-policy-help')!.textContent
  expect(description).toContain(`Worker metadata visibility: ${help}`)
  expect(description).toContain('does not reveal the API key or allow others to claim as this worker')
  expect(description).toContain('Job access policies determine which jobs it can claim.')
  mockApi(async (path, options) => path === '/api/workers' && options?.method === 'POST'
    ? response({ ...worker, secret_api_key: 'new-key' }) : undefined)
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
  expect(screen.getByRole('list', { name: 'Selected supported types' }).textContent).toContain('sum')
  fireEvent.change(screen.getByLabelText('Worker name'), { target: { value: 'another-worker' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Register a worker' }))
  expect(await screen.findByRole('heading', { name: 'another-worker registered' })).toBeTruthy()
})

test.each(['', '  ', 'a'.repeat(101)])('rejects invalid supported types %j before registration', async (types) => {
  await enterApp('/workers/new')
  fillWorkerRegistration(types)
  expect(screen.getByRole('alert').textContent).toContain('at least one non-blank supported type')
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

test('adds and removes supported-type tags without submitting, preserving exact values and removing duplicates', async () => {
  mockApi(async (path, options) => path === '/api/workers' && options?.method === 'POST'
    ? response({ ...worker, secret_api_key: 'new-key' }) : undefined)
  await enterApp('/workers/new')
  const input = screen.getByLabelText('Supported types')
  fireEvent.change(screen.getByLabelText('Worker name'), { target: { value: worker.name } })
  for (const type of ['sum', 'sum', ' Sum with spaces ']) {
    fireEvent.change(input, { target: { value: type } })
    fireEvent.keyDown(input, { key: 'Enter' })
  }
  const tags = screen.getByRole('list', { name: 'Selected supported types' })
  expect(within(tags).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['sum', ' Sum with spaces '])
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/workers')).toBe(false)
  fireEvent.keyDown(input, { key: 'Backspace' })
  expect(within(tags).getAllByRole('listitem')).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Remove type sum' }))
  expect(screen.queryByRole('list', { name: 'Selected supported types' })).toBeNull()
  fireEvent.change(input, { target: { value: 'custom_type' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add' }))
  expect((input as HTMLInputElement).value).toBe('')
  fireEvent.submit(screen.getByRole('form', { name: 'Register a worker' }))
  await screen.findByLabelText('New worker API key')
  const [, options] = fetchMock.mock.calls.find(([path]) => path === '/api/workers')!
  expect(JSON.parse(String(options?.body)).supported_types).toEqual(['custom_type'])
})

test('suggests accessible types with an encoded query and allows new types when suggestions fail', async () => {
  mockApi(async (path, options) => {
    if (String(path).startsWith('/api/job-types?')) {
      const query = new URL(String(path), 'http://localhost').searchParams
      return query.get('query') === 'sum & more' ? response(['sum & more']) : response({}, 503)
    }
    if (path === '/api/workers' && options?.method === 'POST') return response({ ...worker, secret_api_key: 'new-key' })
  })
  await enterApp('/workers/new')
  const input = screen.getByLabelText('Supported types')
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: 'sum & more' } })
  await screen.findByRole('option', { name: 'sum & more', hidden: true })
  const [, options] = fetchMock.mock.calls.find(([path]) => String(path) === '/api/job-types?limit=10&query=sum+%26+more')!
  expect(new Headers(options?.headers).get('Authorization')).toMatch(/^Bearer /)
  fireEvent.change(input, { target: { value: 'brand_new_type' } })
  await waitFor(() => expect(fetchMock.mock.calls.some(([path]) => path === '/api/job-types?limit=10&query=brand_new_type')).toBe(true))
  fireEvent.change(screen.getByLabelText('Worker name'), { target: { value: worker.name } })
  fireEvent.submit(screen.getByRole('form', { name: 'Register a worker' }))
  await screen.findByLabelText('New worker API key')
  const [, created] = fetchMock.mock.calls.find(([path]) => path === '/api/workers')!
  expect(JSON.parse(String(created?.body)).supported_types).toEqual(['brand_new_type'])
})

test('edits owned worker types and visibility and refreshes details and cached lists', async () => {
  let current = { ...worker }
  mockApi(async (path, options) => {
    if (path === '/api/workers/17' && options?.method === 'PUT') {
      current = { ...current, ...JSON.parse(String(options.body)) }
      return response(current)
    }
    if (path === '/api/workers/17') return response(current)
    if (String(path).startsWith('/api/workers?')) return response([current])
  })
  await enterApp('/workers')
  fireEvent.click(await screen.findByRole('link', { name: worker.name }))
  fireEvent.click(await screen.findByRole('link', { name: 'Edit worker' }))
  const form = await screen.findByRole('form', { name: 'Edit worker' })
  expect(window.location.pathname).toBe('/workers/17/edit')
  expect((screen.getByLabelText('Worker name') as HTMLInputElement).readOnly).toBe(true)
  expect(within(screen.getByRole('list', { name: 'Selected supported types' })).getAllByRole('listitem').map((item) => item.textContent)).toEqual(worker.supported_types)
  fireEvent.click(screen.getByRole('button', { name: 'Remove type sum' }))
  fireEvent.change(screen.getByLabelText('Supported types'), { target: { value: ' CSV summary ' } })
  fireEvent.change(screen.getByLabelText('Visibility policy'), { target: { value: 'ALL' } })
  fireEvent.submit(form)
  const details = await screen.findByRole('region', { name: 'Worker metadata' })
  expect(window.location.pathname).toBe('/workers/17')
  expect(details.textContent).toContain('All users')
  expect(within(details).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['add_numbers', ' CSV summary '])
  const [, options] = fetchMock.mock.calls.find(([, options]) => options?.method === 'PUT')!
  expect(JSON.parse(String(options?.body))).toEqual({ supported_types: ['add_numbers', ' CSV summary '], permission_policy: 'ALL' })
  expect(new Headers(options?.headers).get('Authorization')).toMatch(/^Bearer /)
  fireEvent.click(screen.getByRole('link', { name: 'Back to Workers' }))
  const table = await screen.findByRole('table', { name: 'Registered workers' })
  await waitFor(() => expect(table.textContent).toContain('CSV summary'))
  expect(table.textContent).toContain('All users')
  expect(table.textContent).not.toContain('add_numbers, sum')
})

test('cancels an edit without changing the worker', async () => {
  await enterApp('/workers/17/edit')
  await screen.findByRole('form', { name: 'Edit worker' })
  fireEvent.click(screen.getByRole('button', { name: 'Remove type sum' }))
  fireEvent.change(screen.getByLabelText('Visibility policy'), { target: { value: 'ALL' } })
  fireEvent.click(screen.getByRole('link', { name: 'Cancel' }))
  const details = await screen.findByRole('region', { name: 'Worker metadata' })
  expect(within(details).getAllByRole('listitem').map((item) => item.textContent)).toEqual(worker.supported_types)
  expect(details.textContent).toContain('Private')
  expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PUT')).toBe(false)
})

test.each(['shared', 'missing', 'invalid'])('blocks editing a %s worker', async (kind) => {
  mockApi(async (path) => path === '/api/workers/17'
    ? kind === 'shared' ? response({ ...worker, user_id: 888 }) : response({ detail: 'Worker not found' }, 404)
    : undefined)
  await enterApp(kind === 'invalid' ? '/workers/invalid/edit' : '/workers/17/edit')
  await screen.findByRole('heading', { name: 'Worker unavailable' })
  expect(screen.queryByRole('form', { name: 'Edit worker' })).toBeNull()
  expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PUT')).toBe(false)
  if (kind === 'invalid') expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith('/api/workers'))).toBe(false)
})

test('requires at least one type when editing', async () => {
  await enterApp('/workers/17/edit')
  const form = await screen.findByRole('form', { name: 'Edit worker' })
  for (const type of worker.supported_types) fireEvent.click(screen.getByRole('button', { name: `Remove type ${type}` }))
  fireEvent.submit(form)
  expect(screen.getByRole('alert').textContent).toContain('at least one non-blank supported type')
  expect(screen.getByLabelText('Supported types').getAttribute('aria-invalid')).toBe('true')
  expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PUT')).toBe(false)
})

test.each([422, 503])('preserves an edit after HTTP %s and allows manual retry', async (status) => {
  let failed = false
  let saved = false
  mockApi(async (path, options) => {
    if (path === '/api/workers/17' && options?.method === 'PUT') {
      if (!failed) {
        failed = true
        return response(status === 422 ? { detail: [{ loc: ['body', 'supported_types', 0], msg: 'Unsupported value', type: 'value_error' }] } : {}, status)
      }
      saved = true
      return response({ ...worker, supported_types: ['add_numbers', 'sum', 'custom'] })
    }
    if (path === '/api/workers/17' && saved) return response({ ...worker, supported_types: ['add_numbers', 'sum', 'custom'] })
  })
  await enterApp('/workers/17/edit')
  const form = await screen.findByRole('form', { name: 'Edit worker' })
  fireEvent.change(screen.getByLabelText('Supported types'), { target: { value: 'custom' } })
  fireEvent.submit(form)
  expect((await screen.findByRole('alert')).textContent).toContain(status === 422 ? 'Unsupported value' : 'temporarily unavailable')
  if (status === 422) expect(document.getElementById('worker-types-error')?.textContent).toBe('Unsupported value')
  expect((screen.getByLabelText('Supported types') as HTMLInputElement).value).toBe('custom')
  expect(screen.getByRole('list', { name: 'Selected supported types' }).children).toHaveLength(2)
  expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(1)
  fireEvent.submit(form)
  const details = await screen.findByRole('region', { name: 'Worker metadata' })
  expect(details.textContent).toContain('custom')
  const requests = fetchMock.mock.calls.filter(([, options]) => options?.method === 'PUT')
  expect(requests).toHaveLength(2)
  expect(requests[0][1]?.body).toBe(requests[1][1]?.body)
})

test.each(['navigate', 'logout'])('prevents duplicate edits and cancels pending save on %s', async (action) => {
  let resolve!: (value: Response) => void
  mockApi(async (path, options) => path === '/api/workers/17' && options?.method === 'PUT'
    ? new Promise((done) => { resolve = done }) : undefined)
  await enterApp('/workers/17/edit')
  const form = await screen.findByRole('form', { name: 'Edit worker' })
  fireEvent.submit(form)
  expect((screen.getByRole('button', { name: 'Saving…' }) as HTMLButtonElement).matches(':disabled')).toBe(true)
  fireEvent.submit(form)
  const updates = fetchMock.mock.calls.filter(([, options]) => options?.method === 'PUT')
  expect(updates).toHaveLength(1)
  if (action === 'navigate') fireEvent.click(screen.getByRole('link', { name: 'Back to Workers' }))
  else fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(updates[0][1]?.signal?.aborted).toBe(true)
  await act(async () => { resolve(response(worker)) })
  expect(window.location.pathname).toBe(action === 'navigate' ? '/workers' : '/login')
  expect(screen.queryByRole('form', { name: 'Edit worker' })).toBeNull()
})

test.each(['/workers/new', '/workers/17/edit'])('always shows the user input and enables it explicitly at %s', async (route) => {
  await enterApp(route)
  const input = await screen.findByLabelText('Permitted users') as HTMLInputElement
  expect((screen.getByLabelText('Visibility policy') as HTMLSelectElement).value).toBe('PRIVATE')
  expect(input.disabled).toBe(true)
  expect(input.closest('[hidden]')).toBeNull()
  expect(screen.getByRole('button', { name: 'Add user' }).matches(':disabled')).toBe(true)
  expect(screen.getByText(/Choose Permitted users as the visibility policy/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Choose permitted users' }))
  expect((screen.getByLabelText('Visibility policy') as HTMLSelectElement).value).toBe('PERMITTED_USERS')
  expect(input.disabled).toBe(false)
  expect(screen.queryByRole('button', { name: 'Choose permitted users' })).toBeNull()
  await selectPermittedUser('alex')
  fireEvent.change(input, { target: { value: 'mar' } })
  for (const policy of ['PRIVATE', 'ALL']) {
    fireEvent.change(screen.getByLabelText('Visibility policy'), { target: { value: policy } })
    expect(screen.getByLabelText('Permitted users')).toBe(input)
    expect(input.disabled).toBe(true)
    expect(input.value).toBe('mar')
    expect(screen.getByRole('button', { name: 'Remove alex' }).matches(':disabled')).toBe(true)
  }
  fireEvent.click(screen.getByRole('button', { name: 'Choose permitted users' }))
  expect(input.disabled).toBe(false)
  expect(input.value).toBe('mar')
  expect(screen.getByRole('button', { name: 'Remove alex' }).matches(':disabled')).toBe(false)
})

test.each(['register', 'edit'])('uses user tags and username suggestions to %s worker grants', async (mode) => {
  const editing = mode === 'edit'
  let saved = false
  mockApi(async (path, options) => {
    if (path === '/api/workers/17' && options?.method === 'PUT') { saved = true; return response(worker) }
    if (path === '/api/workers/17') return response({ ...worker, permission_policy: 'PERMITTED_USERS', permitted_user_ids: saved ? [12] : [15] })
    if (path === '/api/workers' && options?.method === 'POST') return response({ ...worker, secret_api_key: 'new-key' })
  })
  await enterApp(editing ? '/workers/17/edit' : '/workers/new')
  const form = await screen.findByRole('form', { name: editing ? 'Edit worker' : 'Register a worker' })
  if (editing) {
    await waitFor(() => expect(screen.getByRole('list', { name: 'Selected permitted users' }).textContent).toContain('maria'))
    fireEvent.click(screen.getByRole('button', { name: 'Remove maria' }))
  } else {
    fireEvent.change(screen.getByLabelText('Visibility policy'), { target: { value: 'PERMITTED_USERS' } })
    fireEvent.change(screen.getByLabelText('Worker name'), { target: { value: worker.name } })
    fireEvent.change(screen.getByLabelText('Supported types'), { target: { value: 'add_numbers' } })
  }
  const input = screen.getByLabelText('Permitted users')
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: 'ale' } })
  const suggestion = await screen.findByRole('option', { name: 'alex Alex Example' })
  expect(suggestion.textContent).not.toContain('12')
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/users?limit=10&query=ale')).toBe(true)
  // Choose the highlighted username with Enter, without entering an ID.
  fireEvent.keyDown(input, { key: 'Enter' })
  await waitFor(() => expect(screen.getByRole('list', { name: 'Selected permitted users' }).textContent).toContain('alex'))
  expect((input as HTMLInputElement).value).toBe('')
  // Already selected users are excluded from suggestions.
  fireEvent.change(input, { target: { value: 'alex' } })
  await screen.findByText('No matching users to add.')
  expect(screen.queryByRole('option', { name: 'alex Alex Example' })).toBeNull()
  await selectPermittedUser('maria')
  expect(within(screen.getByRole('list', { name: 'Selected permitted users' })).getAllByRole('listitem')).toHaveLength(2)
  fireEvent.keyDown(input, { key: 'Backspace' })
  expect(screen.queryByRole('button', { name: 'Remove maria' })).toBeNull()
  fireEvent.submit(form)
  if (editing) await screen.findByRole('region', { name: 'Worker metadata' })
  else await screen.findByLabelText('New worker API key')
  const [, options] = fetchMock.mock.calls.find(([path, options]) => path === (editing ? '/api/workers/17' : '/api/workers')
    && options?.method === (editing ? 'PUT' : 'POST'))!
  expect(JSON.parse(String(options?.body))).toMatchObject({ permission_policy: 'PERMITTED_USERS', permitted_user_ids: [12] })
})

test.each(['/workers/new', '/workers/17/edit'])('requires choosing a username instead of accepting raw IDs at %s', async (route) => {
  await enterApp(route)
  const form = await screen.findByRole('form', { name: route.endsWith('/edit') ? 'Edit worker' : 'Register a worker' })
  fireEvent.click(screen.getByRole('button', { name: 'Choose permitted users' }))
  if (route.endsWith('/new')) {
    fireEvent.change(screen.getByLabelText('Worker name'), { target: { value: worker.name } })
    fireEvent.change(screen.getByLabelText('Supported types'), { target: { value: 'add_numbers' } })
  }
  const input = screen.getByRole('combobox', { name: 'Permitted users' })
  expect((input as HTMLInputElement).placeholder).toBe('Search by username')
  expect(screen.queryByLabelText('Permitted user IDs')).toBeNull()
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: '12' } })
  await screen.findByText('No matching users to add.')
  expect(screen.getByRole('button', { name: 'Add user' }).matches(':disabled')).toBe(true)
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(screen.queryByRole('list', { name: 'Selected permitted users' })).toBeNull()
  fireEvent.submit(form)
  expect(screen.getByRole('alert').textContent).toContain('Select a user from the suggestions')
  expect(fetchMock.mock.calls.some(([path, options]) => String(path).startsWith('/api/workers') && ['POST', 'PUT'].includes(options?.method ?? ''))).toBe(false)
})

test('selects users with arrow keys and Enter and reopens suggestions after Escape', async () => {
  await enterApp('/workers/new')
  fireEvent.click(screen.getByRole('button', { name: 'Choose permitted users' }))
  const input = screen.getByRole('combobox', { name: 'Permitted users' })
  fireEvent.focus(input)
  await screen.findByRole('option', { name: 'maria Maria Example' })
  fireEvent.keyDown(input, { key: 'ArrowDown' })
  expect(screen.getByRole('option', { name: 'maria Maria Example' }).getAttribute('aria-selected')).toBe('true')
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(screen.getByRole('button', { name: 'Remove maria' })).toBeTruthy()
  fireEvent.keyDown(input, { key: 'Escape' })
  expect(screen.queryByRole('listbox', { name: 'User suggestions' })).toBeNull()
  fireEvent.change(input, { target: { value: 'ale' } })
  fireEvent.click(await screen.findByRole('option', { name: 'alex Alex Example' }))
  expect(screen.getByRole('button', { name: 'Remove alex' })).toBeTruthy()
  expect(within(screen.getByRole('list', { name: 'Selected permitted users' })).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['maria', 'alex'])
})

test('retries failed user searches without discarding selected usernames', async () => {
  let failed = true
  mockApi(async (path) => {
    if (path === '/api/workers/17') return response({ ...worker, permission_policy: 'PERMITTED_USERS', permitted_user_ids: [12] })
    if (String(path).startsWith('/api/users?') && failed) return response({}, 503)
  })
  await enterApp('/workers/17/edit')
  await screen.findByRole('button', { name: 'Remove alex' })
  fireEvent.focus(screen.getByRole('combobox', { name: 'Permitted users' }))
  await screen.findByRole('button', { name: 'Retry user search' })
  expect(screen.getByRole('button', { name: 'Remove alex' })).toBeTruthy()
  failed = false
  fireEvent.click(screen.getByRole('button', { name: 'Retry user search' }))
  fireEvent.click(await screen.findByRole('option', { name: 'maria Maria Example' }))
  expect(screen.getByRole('button', { name: 'Remove maria' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Remove alex' })).toBeTruthy()
})

test('clears all worker user grants and preserves unavailable users until explicitly removed', async () => {
  mockApi(async (path) => path === '/api/workers/17'
    ? response({ ...worker, permission_policy: 'PERMITTED_USERS', permitted_user_ids: [999] }) : undefined)
  await enterApp('/workers/17/edit')
  const form = await screen.findByRole('form', { name: 'Edit worker' })
  await screen.findByText('Unavailable user')
  expect(screen.getByRole('list', { name: 'Selected permitted users' }).textContent).not.toContain('999')
  fireEvent.click(screen.getByRole('button', { name: 'Remove unavailable user' }))
  fireEvent.submit(form)
  await screen.findByRole('region', { name: 'Worker metadata' })
  const [, options] = fetchMock.mock.calls.find(([, options]) => options?.method === 'PUT')!
  expect(JSON.parse(String(options?.body)).permitted_user_ids).toEqual([])
})

test('preserves user tags after rejected worker updates and shows field validation', async () => {
  mockApi(async (path, options) => {
    if (path === '/api/workers/17' && options?.method === 'PUT') return response({
      detail: [{ loc: ['body', 'permitted_user_ids', 0], msg: 'Invalid user ID', type: 'value_error' }],
    }, 422)
    if (path === '/api/workers/17') return response({ ...worker, permission_policy: 'PERMITTED_USERS', permitted_user_ids: [12] })
  })
  await enterApp('/workers/17/edit')
  const form = await screen.findByRole('form', { name: 'Edit worker' })
  fireEvent.submit(form)
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Permitted users').getAttribute('aria-invalid')).toBe('true')
  expect(document.getElementById('worker-user-ids-error')?.textContent).toBe('Invalid user ID')
  expect(await screen.findByRole('button', { name: 'Remove alex' })).toBeTruthy()
  expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(1)
})

test.each(['/workers/17', '/workers/17/edit'])('deletes a worker only after confirmation and refreshes the cached directory from %s', async (route) => {
  let deleted = false
  mockApi(async (path, options) => {
    if (path === '/api/workers/17' && options?.method === 'DELETE') {
      deleted = true
      return new Response(null, { status: 204 })
    }
    if (String(path).startsWith('/api/workers?')) return response(deleted ? [] : [worker])
    if (deleted && path === '/api/workers/17') return response({ detail: 'Worker not found' }, 404)
  })
  await enterApp('/workers')
  fireEvent.click(await screen.findByRole('link', { name: worker.name }))
  await screen.findByRole('region', { name: 'Worker metadata' })
  if (route.endsWith('/edit')) fireEvent.click(screen.getByRole('link', { name: 'Edit worker' }))
  const remove = await screen.findByRole('button', { name: 'Delete worker' })
  fireEvent.click(remove)
  expect(screen.getByText(/permanently deletes the worker registration/)).toBeTruthy()
  expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'DELETE')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Cancel deletion' }))
  expect(screen.queryByRole('region', { name: 'Confirm worker deletion' })).toBeNull()
  expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'DELETE')).toBe(false)
  fireEvent.click(remove)
  fireEvent.click(screen.getByRole('button', { name: 'Confirm deletion' }))
  await screen.findByText('No accessible workers match these filters.')
  expect(window.location.pathname).toBe('/workers')
  expect(screen.queryByRole('link', { name: worker.name })).toBeNull()
  const requests = fetchMock.mock.calls.filter(([, options]) => options?.method === 'DELETE')
  expect(requests).toHaveLength(1)
  expect(requests[0][0]).toBe('/api/workers/17')
  expect(new Headers(requests[0][1]?.headers).get('Authorization')).toMatch(/^Bearer /)
})

test('keeps the worker available when deletion conflicts with jobs or attempts', async () => {
  mockApi(async (path, options) => path === '/api/workers/17' && options?.method === 'DELETE'
    ? response({ detail: 'Worker is referenced by jobs or attempts' }, 409) : undefined)
  await enterApp('/workers/17')
  fireEvent.click(await screen.findByRole('button', { name: 'Delete worker' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm deletion' }))
  expect((await screen.findByRole('alert')).textContent).toContain('referenced by jobs or execution attempts and cannot be deleted')
  expect(window.location.pathname).toBe('/workers/17')
  expect(screen.getByRole('region', { name: 'Worker metadata' }).textContent).toContain(worker.name)
  expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'DELETE')).toHaveLength(1)
})

test.each(['network', 'server'])('explains uncertain worker deletion after a %s failure without retrying', async (failure) => {
  mockApi(async (path, options) => {
    if (path === '/api/workers/17' && options?.method === 'DELETE') {
      if (failure === 'network') throw new Error('private diagnostics')
      return response({}, 503)
    }
  })
  await enterApp('/workers/17')
  fireEvent.click(await screen.findByRole('button', { name: 'Delete worker' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm deletion' }))
  await screen.findByRole('alert')
  expect(screen.getByText(/worker may have been deleted/)).toBeTruthy()
  expect(document.body.textContent).not.toContain('private diagnostics')
  expect(window.location.pathname).toBe('/workers/17')
  expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'DELETE')).toHaveLength(1)
})

test.each(['navigate', 'logout'])('prevents duplicate worker deletions and ignores a late response after %s', async (action) => {
  let resolve!: (value: Response) => void
  mockApi(async (path, options) => path === '/api/workers/17' && options?.method === 'DELETE'
    ? new Promise((done) => { resolve = done }) : undefined)
  await enterApp('/workers/17')
  fireEvent.click(await screen.findByRole('button', { name: 'Delete worker' }))
  const confirm = screen.getByRole('button', { name: 'Confirm deletion' })
  fireEvent.click(confirm)
  fireEvent.click(confirm)
  const requests = fetchMock.mock.calls.filter(([, options]) => options?.method === 'DELETE')
  expect(requests).toHaveLength(1)
  expect((screen.getByRole('button', { name: 'Deleting…' }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: 'Reissue API key' }) as HTMLButtonElement).disabled).toBe(true)
  if (action === 'navigate') {
    fireEvent.click(screen.getByRole('link', { name: 'Back to Workers' }))
    await screen.findByRole('link', { name: 'Jobs' })
    fireEvent.click(screen.getByRole('link', { name: 'Jobs' }))
    await screen.findByRole('heading', { level: 1, name: 'Jobs' })
  } else fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(requests[0][1]?.signal?.aborted).toBe(true)
  const location = window.location.pathname
  await act(async () => { resolve(new Response(null, { status: 204 })) })
  expect(window.location.pathname).toBe(location)
})

test.each(['/workers/17', '/workers/17/edit'])('reissues a worker key with confirmation and one-time display at %s', async (route) => {
  const secret = 'reissued-worker-key'
  mockApi(async (path) => path === '/api/workers/17/api-key' ? response({ secret_api_key: secret }) : undefined)
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  const setItem = vi.spyOn(Storage.prototype, 'setItem')
  await enterApp(route)
  const reissue = await screen.findByRole('button', { name: 'Reissue API key' })
  fireEvent.click(reissue)
  expect(screen.getByText(/old key will stop working immediately/)).toBeTruthy()
  expect(fetchMock.mock.calls.some(([path]) => String(path).endsWith('/api-key'))).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Cancel reissue' }))
  expect(screen.queryByRole('region', { name: 'Confirm worker key reissue' })).toBeNull()
  fireEvent.click(reissue)
  fireEvent.click(screen.getByRole('button', { name: 'Confirm reissue' }))
  expect((await screen.findByLabelText('New worker API key')).textContent).toBe(secret)
  const [, options] = fetchMock.mock.calls.find(([path]) => String(path).endsWith('/api-key'))!
  expect(options?.method).toBe('POST')
  expect(new Headers(options?.headers).get('Authorization')).toMatch(/^Bearer /)
  expect(writeText).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Copy API key' }))
  await screen.findByText('API key copied. Save it securely.')
  expect(writeText).toHaveBeenCalledWith(secret)
  expect(setItem.mock.calls.some((args) => args.some((arg) => String(arg).includes(secret)))).toBe(false)
  expect(sessionStorage.length).toBe(0)
  expect(window.location.href).not.toContain(secret)
  cleanup()
  render(<App />)
  await screen.findByRole('button', { name: 'Reissue API key' })
  expect(screen.queryByLabelText('New worker API key')).toBeNull()
  expect(fetchMock.mock.calls.filter(([path]) => String(path).endsWith('/api-key'))).toHaveLength(1)
})

test.each(['network', 'server', 'invalid'])('reports %s key reissue failure without automatic retry', async (failure) => {
  mockApi(async (path) => {
    if (path === '/api/workers/17/api-key') {
      if (failure === 'network') throw new Error('private diagnostics')
      return failure === 'server' ? response({}, 503) : response({ secret_api_key: '' })
    }
  })
  await enterApp('/workers/17')
  fireEvent.click(await screen.findByRole('button', { name: 'Reissue API key' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm reissue' }))
  await screen.findByRole('alert')
  expect(screen.getByText(/old key may already be invalid/)).toBeTruthy()
  expect(screen.queryByLabelText('New worker API key')).toBeNull()
  expect(document.body.textContent).not.toContain('private diagnostics')
  expect(fetchMock.mock.calls.filter(([path]) => String(path).endsWith('/api-key'))).toHaveLength(1)
})

test.each(['navigate', 'logout'])('prevents duplicate worker key reissues and cancels on %s', async (action) => {
  let resolve!: (value: Response) => void
  mockApi(async (path) => path === '/api/workers/17/api-key'
    ? new Promise((done) => { resolve = done }) : undefined)
  await enterApp('/workers/17')
  fireEvent.click(await screen.findByRole('button', { name: 'Reissue API key' }))
  const confirm = screen.getByRole('button', { name: 'Confirm reissue' })
  fireEvent.click(confirm)
  fireEvent.click(confirm)
  const requests = fetchMock.mock.calls.filter(([path]) => String(path).endsWith('/api-key'))
  expect(requests).toHaveLength(1)
  expect((screen.getByRole('button', { name: 'Reissuing…' }) as HTMLButtonElement).disabled).toBe(true)
  if (action === 'navigate') fireEvent.click(screen.getByRole('link', { name: 'Back to Workers' }))
  else fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(requests[0][1]?.signal?.aborted).toBe(true)
  await act(async () => { resolve(response({ secret_api_key: 'late-secret' })) })
  expect(document.body.textContent).not.toContain('late-secret')
})
