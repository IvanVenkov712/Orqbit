// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { StrictMode } from 'react'
import App from './App'
import { AuthProvider, useAuth } from './auth'
import orqbitIcon from './assets/orqbit-icon.svg'

const user = { id: 7, username: 'demo-user', email: 'demo@example.com', full_name: 'Demo User', active: true, role: 'REGULAR' }
const fetchMock = vi.fn<typeof fetch>()
const storageKey = 'orqbit.access_token'
const job = {
  id: 42, user_id: user.id, job_type: 'add_numbers', status: 'SUCCEEDED',
  params: { numbers: [2, 3, 5] }, result: { sum: 10 }, error: null,
  created_at: '2026-11-10T08:00:00Z', updated_at: '2026-11-10T09:30:00Z',
}
const attempt = {
  id: 19, job_id: job.id, worker_id: 12, job_type: job.job_type,
  attempt_number: 1, status: 'SUCCEEDED', params: job.params,
  result: job.result, error: null,
  created_at: '2026-11-10T08:00:00Z', updated_at: '2026-11-10T08:00:01Z',
}

function token(expiresAt = Date.now() + 30 * 60_000) {
  return `header.${btoa(JSON.stringify({ sub: user.username, exp: Math.floor(expiresAt / 1000) }))}.signature`
}

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState(null, '', '/')
  fetchMock.mockReset()
  fetchMock.mockImplementation(async (path) => {
    if (path === '/api/auth/login') return response({ access_token: token(), token_type: 'bearer' })
    if (path === '/api/users/me/' || path === '/api/auth/register') return response(user)
    if (String(path).startsWith('/api/jobs?')) return response([{ ...job, status: new URL(String(path), 'http://localhost').searchParams.get('status') ?? 'PENDING' }])
    if (/^\/api\/jobs\/\d+$/.test(String(path))) return response(job)
    if (String(path).startsWith('/api/jobs/42/attempts?')) return response([attempt])
    throw new Error('Unexpected request')
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function fillLogin() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: user.username } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Example1@' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

async function enterApp(path = '/jobs') {
  window.history.replaceState(null, '', path)
  render(<App />)
  fillLogin()
  await screen.findByRole('button', { name: 'Sign out' })
  await waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).not.toBe('Sign in'))
}

function fillRegistration() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: user.username } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: user.email } })
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: user.full_name } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Example1@' } })
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
}

test('requires login by default and shows the signed-out user area', () => {
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(window.location.pathname).toBe('/login')
  expect(screen.getByRole('group', { name: 'Current user' }).textContent).toContain('Not signed in')
  expect(fetchMock).not.toHaveBeenCalled()
})

test.each(['/login', '/register'])('uses the Orqbit icon on %s without session implementation text', (path) => {
  window.history.replaceState(null, '', path)
  render(<App />)
  const brandIcon = screen.getByRole('link', { name: 'Orqbit home' }).querySelector('img')
  expect(brandIcon?.getAttribute('src')).toBe(orqbitIcon)
  expect(document.querySelector('main img')?.getAttribute('src')).toBe(brandIcon?.getAttribute('src'))
  expect(screen.queryByText(/Your session stays in memory/)).toBeNull()
})

test.each(['/jobs', '/jobs/new', '/jobs/42', '/jobs/42/attempts', '/workers', '/workers/17'])(
  'protects direct entry to %s', (path) => {
    window.history.replaceState(null, '', path)
    render(<App />)
    expect(window.location.pathname).toBe('/login')
    expect(screen.queryByText('Planned screen')).toBeNull()
  },
)

test('logs in with form data, loads the current user, and restores the requested URL', async () => {
  const accessToken = token()
  fetchMock.mockResolvedValueOnce(response({ access_token: accessToken, token_type: 'bearer' }))
  await enterApp('/workers/17?view=details#registration')
  expect(window.location.pathname + window.location.search + window.location.hash).toBe('/workers/17?view=details#registration')
  expect(screen.getByRole('heading', { level: 1, name: 'Worker details' })).toBeTruthy()
  expect(screen.getByRole('group', { name: 'Current user' }).textContent).toBe('Demo User (demo-user)Sign out')
  const [loginPath, loginOptions] = fetchMock.mock.calls[0]
  expect(loginPath).toBe('/api/auth/login')
  expect(loginOptions?.method).toBe('POST')
  expect(String(loginOptions?.body)).toBe('username=demo-user&password=Example1%40')
  expect(new Headers(loginOptions?.headers).get('Content-Type')).toContain('application/x-www-form-urlencoded')
  expect(fetchMock.mock.calls[1][0]).toBe('/api/users/me/')
  expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('Authorization')).toBe(`Bearer ${accessToken}`)
  expect(window.localStorage.length).toBe(1)
  expect(window.localStorage.getItem(storageKey)).toBe(accessToken)
  expect(window.sessionStorage.length).toBe(0)
})

test.each([
  [401, 'Incorrect username or password'],
  [500, 'Orqbit is temporarily unavailable. Please try again later.'],
])('shows a safe login error for HTTP %s', async (status, message) => {
  fetchMock.mockResolvedValueOnce(response({ detail: status === 500 ? 'internal secret' : message }, status))
  render(<App />)
  fillLogin()
  expect((await screen.findByRole('alert')).textContent).toBe(message)
  expect(window.location.pathname).toBe('/login')
  expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('shows a connection error and allows retrying login', async () => {
  fetchMock.mockRejectedValueOnce(new Error('private network diagnostics'))
  render(<App />)
  fillLogin()
  expect((await screen.findByRole('alert')).textContent).toContain('Unable to reach Orqbit')
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Jobs' })).toBeTruthy()
})

test('does not enter the application if loading the current user rejects the credentials', async () => {
  fetchMock.mockResolvedValueOnce(response({ access_token: token() }))
  fetchMock.mockResolvedValueOnce(response({ detail: 'Could not validate credentials' }, 401))
  render(<App />)
  fillLogin()
  expect((await screen.findByRole('alert')).textContent).toBe('Could not validate credentials')
  expect(screen.queryByText('Planned screen')).toBeNull()
})

test('prevents duplicate login requests and cancels a login when leaving the form', async () => {
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  render(<App />)
  fillLogin()
  const button = screen.getByRole('button', { name: 'Signing in…' }) as HTMLButtonElement
  expect(button.matches(':disabled')).toBe(true)
  fireEvent.submit(button.closest('form')!)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  const signal = fetchMock.mock.calls[0][1]?.signal
  fireEvent.click(screen.getByRole('link', { name: 'Create an account' }))
  expect(signal?.aborted).toBe(true)
  await act(async () => { resolve(response({ access_token: token() })) })
  expect(screen.getByRole('heading', { level: 1, name: 'Create an account' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
})

test('navigates between Jobs and Workers and follows browser back/forward', async () => {
  await enterApp()
  fireEvent.click(screen.getByRole('link', { name: 'Workers' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Workers' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Workers' }).getAttribute('aria-current')).toBe('page')
  expect(screen.getByRole('link', { name: 'Jobs' }).hasAttribute('aria-current')).toBe(false)
  await act(async () => { window.history.back() })
  await waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Jobs'))
  await act(async () => { window.history.forward() })
  await waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Workers'))
})

test.each([
  ['/jobs', 'Jobs', 'Jobs'],
  ['/jobs/new', 'Submit a job', 'Jobs'],
  ['/jobs/42', 'Job details', 'Jobs'],
  ['/jobs/42/attempts', 'Attempt history', 'Jobs'],
  ['/workers', 'Workers', 'Workers'],
  ['/workers/17', 'Worker details', 'Workers'],
])('restores %s after login and highlights its section', async (path, title, activeLink) => {
  await enterApp(path)
  expect(screen.getByRole('heading', { level: 1, name: title })).toBeTruthy()
  if (path === '/jobs/new') {
    expect(screen.queryByText('Planned screen')).toBeNull()
    expect(screen.getByRole('form', { name: 'Submit a job' })).toBeTruthy()
  } else if (path === '/jobs/42') {
    expect(screen.queryByText('Planned screen')).toBeNull()
    expect(await screen.findByRole('region', { name: 'Job overview' })).toBeTruthy()
  } else if (path === '/jobs') {
    expect(await screen.findByRole('table', { name: 'Submitted jobs' })).toBeTruthy()
  } else if (path === '/jobs/42/attempts') {
    expect(await screen.findByRole('region', { name: 'Execution attempts' })).toBeTruthy()
  } else {
    expect(screen.getByText('Worker management is not available yet.')).toBeTruthy()
  }
  expect(screen.queryByText(/frontend roadmap|does not load live data|Refreshes every/)).toBeNull()
  expect(screen.getByRole('link', { name: activeLink }).getAttribute('aria-current')).toBe('page')
})

test('signs out and prevents browser back from reopening a protected screen', async () => {
  await enterApp()
  fireEvent.click(screen.getByRole('link', { name: 'Workers' }))
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(screen.queryByText('Demo User (demo-user)')).toBeNull()
  expect(localStorage.getItem(storageKey)).toBeNull()
  await act(async () => { window.history.back() })
  await waitFor(() => expect(window.location.pathname).toBe('/login'))
  expect(screen.queryByText('Planned screen')).toBeNull()
})

test('preserves login and the requested URL after a page reload while validating the current user', async () => {
  const path = '/workers/17?view=details#registration'
  await enterApp(path)
  const accessToken = localStorage.getItem(storageKey)
  cleanup()
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  render(<App />)
  expect(screen.getByRole('status').textContent).toBe('Restoring your session…')
  expect(screen.queryByRole('heading', { level: 1, name: 'Sign in' })).toBeNull()
  expect(screen.queryByText('Planned screen')).toBeNull()
  expect(window.location.pathname + window.location.search + window.location.hash).toBe(path)
  expect(fetchMock.mock.calls[2][0]).toBe('/api/users/me/')
  expect(new Headers(fetchMock.mock.calls[2][1]?.headers).get('Authorization')).toBe(`Bearer ${accessToken}`)
  await act(async () => { resolve(response({ ...user, full_name: 'Updated Name' })) })
  expect(await screen.findByRole('heading', { level: 1, name: 'Worker details' })).toBeTruthy()
  expect(screen.getByRole('group', { name: 'Current user' }).textContent).toContain('Updated Name')
  expect(fetchMock).toHaveBeenCalledTimes(3)
  expect(localStorage.getItem(storageKey)).toBe(accessToken)
})

test.each([401, 403])('clears a stored token rejected by current-user validation with HTTP %s', async (status) => {
  localStorage.setItem(storageKey, token())
  fetchMock.mockResolvedValueOnce(response({ detail: 'Credentials rejected' }, status))
  window.history.replaceState(null, '', '/jobs/42')
  render(<App />)
  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(screen.getByRole('status').textContent).toContain('Your session has expired')
  expect(localStorage.getItem(storageKey)).toBeNull()
  expect(screen.queryByText('Planned screen')).toBeNull()
})

test.each(['malformed-token', token(Date.now() - 60_000)])('clears an invalid or expired stored token without sending it to the API', (accessToken) => {
  localStorage.setItem(storageKey, accessToken)
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(localStorage.getItem(storageKey)).toBeNull()
  expect(fetchMock).not.toHaveBeenCalled()
})

test.each(['network', 'server'])('keeps the stored token on a %s restoration failure and offers retry', async (failure) => {
  const accessToken = token()
  localStorage.setItem(storageKey, accessToken)
  if (failure === 'network') fetchMock.mockRejectedValueOnce(new Error('Private diagnostics'))
  else fetchMock.mockResolvedValueOnce(response({ detail: 'Internal diagnostics' }, 503))
  window.history.replaceState(null, '', '/workers/17')
  render(<App />)
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(localStorage.getItem(storageKey)).toBe(accessToken)
  expect(window.location.pathname).toBe('/workers/17')
  expect(screen.queryByRole('heading', { level: 1, name: 'Sign in' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Worker details' })).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(fetchMock.mock.calls.every(([path]) => path === '/api/users/me/')).toBe(true)
})

test('logout during restoration cancels the request and prevents a late response restoring the session', async () => {
  localStorage.setItem(storageKey, token())
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  render(<App />)
  const signal = fetchMock.mock.calls[0][1]?.signal
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(signal?.aborted).toBe(true)
  expect(localStorage.getItem(storageKey)).toBeNull()
  await act(async () => { resolve(response(user)) })
  expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  cleanup()
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('restores a saved session in React StrictMode despite its initial effect cleanup', async () => {
  localStorage.setItem(storageKey, token())
  window.history.replaceState(null, '', '/jobs')
  render(<StrictMode><App /></StrictMode>)
  expect(await screen.findByRole('heading', { level: 1, name: 'Jobs' })).toBeTruthy()
  expect(localStorage.getItem(storageKey)).not.toBeNull()
  expect(screen.queryByRole('alert')).toBeNull()
})

test('removes a restored session when its original token expires', async () => {
  vi.useFakeTimers()
  localStorage.setItem(storageKey, token(Date.now() + 60_000))
  await act(async () => { render(<App />) })
  expect(screen.getByRole('heading', { level: 1, name: 'Jobs' })).toBeTruthy()
  await act(async () => { vi.advanceTimersByTime(60_000) })
  expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(localStorage.getItem(storageKey)).toBeNull()
})

test('automatically removes an expired session and allows signing in again', async () => {
  vi.useFakeTimers()
  fetchMock.mockResolvedValueOnce(response({ access_token: token(Date.now() + 60_000) }))
  render(<App />)
  await act(async () => { fillLogin() })
  expect(screen.getByRole('heading', { level: 1, name: 'Jobs' })).toBeTruthy()
  await act(async () => { vi.advanceTimersByTime(60_000) })
  expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(screen.getByRole('status').textContent).toContain('Your session has expired')
  expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
  expect(localStorage.getItem(storageKey)).toBeNull()
  await act(async () => { fillLogin() })
  expect(screen.getByRole('heading', { level: 1, name: 'Jobs' })).toBeTruthy()
})

test.each(['malformed-token', token(Date.now() - 60_000)])('rejects an invalid or already expired session response', async (accessToken) => {
  fetchMock.mockResolvedValueOnce(response({ access_token: accessToken }))
  render(<App />)
  fillLogin()
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(window.location.pathname).toBe('/login')
  expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
})

test('registers with JSON, directs the user to login, and then enters the requested route', async () => {
  window.history.replaceState(null, '', '/workers/17')
  render(<App />)
  fireEvent.click(screen.getByRole('link', { name: 'Create an account' }))
  fillRegistration()
  expect((await screen.findByRole('status')).textContent).toContain('Account created')
  expect(window.location.pathname).toBe('/login')
  expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
  expect(fetchMock).toHaveBeenCalledTimes(1)
  const [path, options] = fetchMock.mock.calls[0]
  expect(path).toBe('/api/auth/register')
  expect(options?.method).toBe('POST')
  expect(JSON.parse(String(options?.body))).toEqual({ username: user.username, email: user.email, full_name: user.full_name, password: 'Example1@' })
  expect(new Headers(options?.headers).get('Content-Type')).toBe('application/json')
  expect(new Headers(options?.headers).has('Authorization')).toBe(false)
  expect((screen.getByLabelText('Password') as HTMLInputElement).value).toBe('')
  fillLogin()
  expect(await screen.findByRole('heading', { level: 1, name: 'Worker details' })).toBeTruthy()
})

test.each(['username', 'email'])('shows duplicate-%s registration errors', async (field) => {
  const message = `User with ${field} already exists`
  fetchMock.mockResolvedValueOnce(response({ detail: message }, 400))
  window.history.replaceState(null, '', '/register')
  render(<App />)
  fillRegistration()
  expect((await screen.findByRole('alert')).textContent).toBe(message)
  expect(window.location.pathname).toBe('/register')
  expect((screen.getByRole('button', { name: 'Create account' }) as HTMLButtonElement).disabled).toBe(false)
})

test('associates backend registration validation with fields without exposing rejected inputs', async () => {
  fetchMock.mockResolvedValueOnce(response({ detail: [
    { loc: ['body', 'password'], msg: 'String should match pattern', type: 'string_pattern_mismatch', input: 'private-password' },
    { loc: ['body', 'email'], msg: 'Invalid email address', type: 'value_error' },
  ] }, 422))
  window.history.replaceState(null, '', '/register')
  render(<App />)
  fillRegistration()
  expect((await screen.findByRole('alert')).textContent).toContain('password: String should match pattern')
  expect(screen.getByLabelText('Password').getAttribute('aria-invalid')).toBe('true')
  expect(document.getElementById('password-error')?.textContent).toBe('String should match pattern')
  expect(document.getElementById('email-error')?.textContent).toBe('Invalid email address')
  expect(document.body.textContent).not.toContain('private-password')
})

test('provides labeled required fields and native email and username validation', () => {
  window.history.replaceState(null, '', '/register')
  render(<App />)
  for (const name of ['Username', 'Email', 'Full name', 'Password']) {
    expect((screen.getByLabelText(name) as HTMLInputElement).required).toBe(true)
  }
  const email = screen.getByLabelText('Email') as HTMLInputElement
  fireEvent.change(email, { target: { value: 'invalid-email' } })
  expect(email.checkValidity()).toBe(false)
  const username = screen.getByLabelText('Username') as HTMLInputElement
  fireEvent.change(username, { target: { value: 'invalid user' } })
  expect(username.checkValidity()).toBe(false)
  fireEvent.change(username, { target: { value: 'demo-user' } })
  expect(username.checkValidity()).toBe(true)
})

test('offers recovery from an unknown route', async () => {
  window.history.replaceState(null, '', '/missing/page')
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeTruthy()
  fireEvent.click(screen.getByRole('link', { name: 'Back to Jobs' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
})

test('links to job submission after authentication', async () => {
  await enterApp()
  fireEvent.click(screen.getByRole('link', { name: 'Submit a job' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Submit a job' })).toBeTruthy()
})

function addParameter(name: string | undefined, value: unknown, path = 'Parameters', index = 1) {
  fireEvent.click(screen.getByRole('button', { name: `Add ${name === undefined ? 'item' : 'parameter'} to ${path}` }))
  const title = `${path} ${index}`
  if (name !== undefined) fireEvent.change(screen.getByLabelText(`Name for ${title}`), { target: { value: name } })
  const type = value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value === 'string' ? 'text' : typeof value
  fireEvent.change(screen.getByLabelText(`Type for ${title}`), { target: { value: type } })
  if (Array.isArray(value)) {
    value.forEach((item, i) => addParameter(undefined, item, `${title} items`, i + 1))
  } else if (value !== null && typeof value === 'object') {
    Object.entries(value).forEach(([key, item], i) => addParameter(key, item, `${title} fields`, i + 1))
  } else if (value !== null) {
    fireEvent.change(screen.getByLabelText(`Value for ${title}`), { target: { value: String(value) } })
  }
}

function fillJob(params: Record<string, unknown> = { numbers: [2, 3, 5] }, jobType = 'add_numbers') {
  fireEvent.change(screen.getByLabelText('Job type'), { target: { value: jobType } })
  for (const button of screen.queryAllByRole('button', { name: /^Remove Parameters \d+$/ })) fireEvent.click(button)
  Object.entries(params).forEach(([name, value], i) => addParameter(name, value, 'Parameters', i + 1))
}

function submitJob() {
  fireEvent.submit(screen.getByRole('form', { name: 'Submit a job' }))
}

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
  expect(screen.getByLabelText('Access policy').querySelectorAll('option')).toHaveLength(1)
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

test('lists the current user’s jobs with owner, type, status, readable dates, and links to details', async () => {
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (path, options) => String(path).startsWith('/api/jobs?')
    ? response([{ ...job, status: 'PENDING' }, { ...job, id: 43, job_type: 'generate_report', status: 'PENDING' }, { ...job, id: 44, status: 'PENDING', user_id: 999 }, { ...job, id: 45, status: 'FAILED' }])
    : original(path, options))
  await enterApp()
  const table = await screen.findByRole('table', { name: 'Submitted jobs' })
  expect(within(table).getAllByRole('columnheader').map((header) => header.textContent)).toEqual(['Owner', 'Type', 'Status', 'Created', 'Last updated'])
  expect(within(table).getAllByText('demo-user')).toHaveLength(2)
  expect(within(table).getByText('generate_report')).toBeTruthy()
  expect(within(table).getAllByText('Pending')).toHaveLength(2)
  const dates = within(table).getByRole('link', { name: 'View job #42' }).closest('tr')!.querySelectorAll('time')
  expect([...dates].map((date) => date.dateTime)).toEqual([job.created_at, job.updated_at])
  expect(dates[0].textContent).toBe(new Date(job.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }))
  expect(dates[1].textContent).toBe(new Date(job.updated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }))
  expect(screen.queryByRole('link', { name: 'View job #44' })).toBeNull()
  expect(screen.queryByRole('link', { name: 'View job #45' })).toBeNull()
  expect(within(screen.getByRole('navigation', { name: 'Job statuses' })).getByRole('link', { name: 'Pending' }).getAttribute('aria-current')).toBe('page')
  const request = fetchMock.mock.calls.find(([path]) => path === '/api/jobs?owner_id=7&limit=20&offset=0&sort=status_updated&status=PENDING')
  expect(request).toBeTruthy()
  expect(new Headers(request?.[1]?.headers).get('Authorization')).toMatch(/^Bearer /)
  fireEvent.click(within(table).getByRole('link', { name: 'View job #42' }))
  await screen.findByRole('region', { name: 'Job overview' })
  expect(window.location.pathname).toBe('/jobs/42')
  fireEvent.click(screen.getByRole('link', { name: 'Back to Jobs' }))
  await screen.findByRole('table', { name: 'Submitted jobs' })
  expect(window.location.pathname).toBe('/jobs')
})

test('navigates between statuses, resets pagination, and restores each view with browser history', async () => {
  const original = fetchMock.getMockImplementation()!
  const page = [
    { ...job, id: 10, status: 'PENDING', updated_at: '2026-11-10T10:00:00Z' },
    { ...job, id: 20, status: 'PENDING', updated_at: '2026-11-10T08:00:00Z' },
    { ...job, id: 30, status: 'RUNNING', updated_at: '2026-11-10T09:00:00Z' },
    { ...job, id: 40, status: 'SUCCEEDED', updated_at: '2026-11-10T11:00:00Z' },
    { ...job, id: 50, status: 'SUCCEEDED', updated_at: '2026-11-10T07:00:00Z' },
    { ...job, id: 60, status: 'FAILED', updated_at: '2026-11-10T12:00:00Z' },
  ]
  fetchMock.mockImplementation(async (path, options) => String(path).startsWith('/api/jobs?')
    ? response(page.filter((job) => job.status === new URL(String(path), 'http://localhost').searchParams.get('status')))
    : original(path, options))
  await enterApp('/jobs?view=recent&offset=20')
  const table = await screen.findByRole('table', { name: 'Submitted jobs' })
  expect(within(table).getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual(['/jobs/10', '/jobs/20'])
  expect(within(table).queryByRole('columnheader', { name: 'Name' })).toBeNull()
  const navigation = screen.getByRole('navigation', { name: 'Job statuses' })
  expect(within(navigation).getAllByRole('link').map((link) => link.textContent)).toEqual(['Pending', 'Running', 'Succeeded', 'Failed'])
  fireEvent.click(within(navigation).getByRole('link', { name: 'Succeeded' }))
  await screen.findByRole('link', { name: 'View job #40' })
  expect(window.location.search).toBe('?view=recent&status=SUCCEEDED')
  expect(screen.queryByRole('link', { name: 'View job #10' })).toBeNull()
  expect(within(screen.getByRole('table')).getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual(['/jobs/40', '/jobs/50'])
  expect(within(navigation).getByRole('link', { name: 'Succeeded' }).getAttribute('aria-current')).toBe('page')
  await act(async () => { window.history.back() })
  await screen.findByRole('link', { name: 'View job #10' })
  expect(window.location.search).toBe('?view=recent&offset=20')
  await act(async () => { window.history.forward() })
  await screen.findByRole('link', { name: 'View job #40' })
  expect(window.location.search).toBe('?view=recent&status=SUCCEEDED')
})

test.each([
  ['PENDING', 'Pending'], ['RUNNING', 'Running'], ['SUCCEEDED', 'Succeeded'], ['FAILED', 'Failed'],
])('opens the %s jobs view directly and preserves it on reload', async (status, label) => {
  const path = `/jobs?status=${status}`
  await enterApp(path)
  await screen.findByRole('table', { name: 'Submitted jobs' })
  expect(screen.getByRole('heading', { level: 2, name: label })).toBeTruthy()
  expect(screen.getByRole('navigation', { name: 'Job statuses' }).querySelector('[aria-current="page"]')?.textContent).toBe(label)
  const query = new URL(String(fetchMock.mock.calls.find(([url]) => String(url).startsWith('/api/jobs?'))![0]), 'http://localhost').searchParams
  expect(query.get('status')).toBe(status)
  expect(query.get('owner_id')).toBe(String(user.id))
  expect(query.get('sort')).toBe('status_updated')
  cleanup()
  render(<App />)
  await screen.findByRole('table', { name: 'Submitted jobs' })
  expect(window.location.pathname + window.location.search).toBe(path)
  expect(screen.getByRole('navigation', { name: 'Job statuses' }).querySelector('[aria-current="page"]')?.textContent).toBe(label)
})

test('falls back to Pending for an unknown status', async () => {
  await enterApp('/jobs?status=UNKNOWN')
  await screen.findByRole('table', { name: 'Submitted jobs' })
  expect(screen.getByRole('heading', { level: 2, name: 'Pending' })).toBeTruthy()
  expect(fetchMock.mock.calls.some(([path]) => String(path).endsWith('&status=PENDING'))).toBe(true)
})

test('shows a clear empty jobs list and keeps submission available', async () => {
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (path, options) => String(path).startsWith('/api/jobs?') ? response([]) : original(path, options))
  await enterApp()
  await screen.findByText('No pending jobs.')
  expect(screen.getByRole('link', { name: 'Submit a job' })).toBeTruthy()
  expect(screen.queryByRole('navigation', { name: 'Job pages' })).toBeNull()
})

test('shows loading and allows retry when the jobs list request fails', async () => {
  localStorage.setItem(storageKey, token())
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(async () => response(user))
  fetchMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  window.history.replaceState(null, '', '/jobs')
  render(<App />)
  await screen.findByText('Loading jobs…')
  await act(async () => { resolve(response({ detail: 'internal details' }, 503)) })
  expect((await screen.findByRole('alert')).textContent).toContain('temporarily unavailable')
  expect(document.body.textContent).not.toContain('internal details')
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByRole('link', { name: 'View job #42' })
})

test('pages through all own jobs, preserves the URL, and handles the final empty page', async () => {
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (path, options) => {
    if (String(path).startsWith('/api/jobs?')) {
      const query = new URL(String(path), 'http://localhost').searchParams
      expect(query.get('owner_id')).toBe(String(user.id))
      expect(query.get('status')).toBe('FAILED')
      return response(query.get('offset') === '0' ? Array.from({ length: 20 }, (_, i) => ({ ...job, id: i + 1, status: 'FAILED' })) : [])
    }
    return original(path, options)
  })
  await enterApp('/jobs?status=FAILED&view=all')
  await screen.findByRole('link', { name: 'View job #20' })
  fireEvent.click(screen.getByRole('button', { name: 'Next jobs' }))
  await screen.findByText('No more jobs on this page.')
  expect(window.location.search).toBe('?status=FAILED&view=all&offset=20')
  expect((screen.getByRole('button', { name: 'Next jobs' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Previous jobs' }))
  await screen.findByRole('link', { name: 'View job #20' })
  expect(window.location.search).toBe('?status=FAILED&view=all')
})

test.each(['-1', 'abc', '1.5', '9007199254740992'])('loads the first jobs page for invalid offset %s', async (offset) => {
  await enterApp(`/jobs?offset=${offset}`)
  await screen.findByRole('table', { name: 'Submitted jobs' })
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/jobs?owner_id=7&limit=20&offset=0&sort=status_updated&status=PENDING')).toBe(true)
})

test('shows only the latest attempt on details and opens the separate paginated history', async () => {
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (path, options) => {
    if (String(path).includes('/attempts?')) {
      const limit = new URL(String(path), 'http://localhost').searchParams.get('limit')
      const attempts = [{ ...attempt, id: 20, attempt_number: 2 }, attempt]
      return response(limit === '1' ? attempts.slice(0, 1) : attempts)
    }
    return original(path, options)
  })
  // A stale history offset in a details link must not hide the latest attempt.
  await enterApp('/jobs/42?offset=10')
  await screen.findByRole('article', { name: 'Attempt 2' })
  expect(screen.queryByRole('article', { name: 'Attempt 1' })).toBeNull()
  expect(screen.queryByRole('navigation', { name: 'Attempt pages' })).toBeNull()
  expect(screen.queryByText(/Refreshes every|while this page is visible/)).toBeNull()
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/jobs/42/attempts?limit=1&offset=0')).toBe(true)
  fireEvent.click(screen.getByRole('link', { name: 'View attempt history' }))
  await screen.findByRole('article', { name: 'Attempt 1' })
  expect(window.location.pathname).toBe('/jobs/42/attempts')
  expect(screen.getAllByRole('article')).toHaveLength(2)
  expect(screen.queryByRole('region', { name: 'Parameters' })).toBeNull()
  fireEvent.click(screen.getByRole('link', { name: 'Back to job' }))
  await screen.findByRole('region', { name: 'Latest attempt' })
  expect(screen.queryByRole('article', { name: 'Attempt 1' })).toBeNull()
})

test('shows no history action when a job has no attempts', async () => {
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (path, options) => String(path).includes('/attempts?') ? response([]) : original(path, options))
  await enterApp('/jobs/42')
  await screen.findByText('No execution attempts yet.')
  expect(screen.queryByRole('link', { name: 'View attempt history' })).toBeNull()
})

test('protects another user’s job when entering attempt history directly', async () => {
  localStorage.setItem(storageKey, token())
  fetchMock.mockImplementation(async (path) => path === '/api/users/me/' ? response(user) : response({ ...job, user_id: 888 }))
  window.history.replaceState(null, '', '/jobs/42/attempts')
  render(<App />)
  await screen.findByRole('heading', { name: 'Job unavailable' })
  expect(fetchMock.mock.calls.some(([path]) => String(path).includes('/attempts?'))).toBe(false)
})

test('shows own job details with a username, formatted parameters, stored result, and attempt outcome', async () => {
  await enterApp('/jobs/42')
  const overview = await screen.findByRole('region', { name: 'Job overview' })
  expect(within(overview).getByText('demo-user (you)')).toBeTruthy()
  expect(overview.textContent).not.toContain('User ID')
  expect(within(overview).getByRole('status').textContent).toBe('Succeeded')
  expect(screen.getByRole('region', { name: 'Parameters' }).textContent).toContain(JSON.stringify(job.params, null, 2))
  expect(screen.getByRole('region', { name: 'Outcome' }).textContent).toContain('"sum": 10')
  const history = screen.getByRole('region', { name: 'Latest attempt' })
  expect(within(history).getByRole('article', { name: 'Attempt 1' }).textContent).toContain('"sum": 10')
  expect(history.querySelector('time')?.dateTime).toBe(attempt.created_at)
  expect(history.textContent).not.toMatch(/worker_id|User ID|Worker ID/)
})

test('shows a failed job and its attempt error as text', async () => {
  const error = { message: '<script>unsafe()</script>', code: 'INVALID_PARAMS' }
  fetchMock.mockImplementation(async (path) => {
    if (path === '/api/auth/login') return response({ access_token: token() })
    if (path === '/api/users/me/') return response(user)
    if (path === '/api/jobs/42') return response({ ...job, status: 'FAILED', result: null, error })
    return response([{ ...attempt, status: 'FAILED', result: null, error }])
  })
  await enterApp('/jobs/42')
  await screen.findByRole('region', { name: 'Job overview' })
  expect(screen.getByRole('status').textContent).toBe('Failed')
  expect(screen.getByRole('region', { name: 'Outcome' }).textContent).toContain(error.message)
  expect(screen.getByRole('article', { name: 'Attempt 1' }).textContent).toContain(error.message)
  expect(document.querySelector('main script')).toBeNull()
})

test.each([403, 404])('shows an unavailable state for an inaccessible or missing job (HTTP %s)', async (status) => {
  localStorage.setItem(storageKey, token())
  fetchMock.mockImplementation(async (path) => path === '/api/users/me/' ? response(user) : response({ detail: 'Job not found' }, status))
  window.history.replaceState(null, '', '/jobs/42')
  render(<App />)
  await screen.findByRole('heading', { name: 'Job unavailable' })
  expect(screen.getByRole('link', { name: 'Back to Jobs' })).toBeTruthy()
  expect(fetchMock.mock.calls.some(([path]) => String(path).includes('/attempts'))).toBe(false)
})

test('does not display another user’s accessible job or fetch its history', async () => {
  localStorage.setItem(storageKey, token())
  fetchMock.mockImplementation(async (path) => path === '/api/users/me/' ? response(user) : response({ ...job, user_id: 888, params: { private: 'other creator data' } }))
  window.history.replaceState(null, '', '/jobs/42')
  render(<App />)
  await screen.findByRole('heading', { name: 'Job unavailable' })
  expect(document.body.textContent).not.toContain('other creator data')
  expect(document.body.textContent).not.toContain('888')
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test.each(['0', '-1', 'abc', '1.5', '9007199254740992'])('rejects invalid job identifier %s without a job request', async (id) => {
  await enterApp(`/jobs/${id}`)
  await screen.findByRole('heading', { name: 'Job unavailable' })
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test('shows loading while fetching details and allows retry after a safe server error', async () => {
  localStorage.setItem(storageKey, token())
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(async () => response(user))
  fetchMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  window.history.replaceState(null, '', '/jobs/42')
  render(<App />)
  await screen.findByText('Loading job details…')
  await act(async () => { resolve(response({ detail: 'private server error' }, 503)) })
  expect((await screen.findByRole('alert')).textContent).toContain('temporarily unavailable')
  expect(document.body.textContent).not.toContain('private server error')
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByRole('region', { name: 'Job overview' })
})

test('paginates attempts in the URL and preserves unrelated query parameters', async () => {
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (path, options) => {
    if (String(path).includes('/attempts?')) {
      const offset = Number(new URL(String(path), 'http://localhost').searchParams.get('offset'))
      return response(offset === 0 ? Array.from({ length: 10 }, (_, i) => ({ ...attempt, id: i + 2, attempt_number: 11 - i })) : [attempt])
    }
    return original(path, options)
  })
  await enterApp('/jobs/42/attempts?view=history')
  await screen.findByRole('article', { name: 'Attempt 11' })
  expect((screen.getByRole('button', { name: 'Previous attempts' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Next attempts' }))
  await screen.findByRole('article', { name: 'Attempt 1' })
  expect(window.location.search).toBe('?view=history&offset=10')
  expect(screen.queryByRole('article', { name: 'Attempt 11' })).toBeNull()
  expect((screen.getByRole('button', { name: 'Next attempts' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Previous attempts' }))
  await screen.findByRole('article', { name: 'Attempt 11' })
  expect(window.location.search).toBe('?view=history')
})

test.each(['-1', 'abc', '1.5', '9007199254740992'])('uses the first attempt page for invalid offset %s', async (offset) => {
  await enterApp(`/jobs/42/attempts?offset=${offset}`)
  await screen.findByRole('region', { name: 'Execution attempts' })
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/jobs/42/attempts?limit=10&offset=0')).toBe(true)
})

test('retains job details when attempt history fails and allows retry', async () => {
  const original = fetchMock.getMockImplementation()!
  let failed = true
  fetchMock.mockImplementation(async (path, options) => {
    if (String(path).includes('/attempts?') && failed) return response({}, 503)
    return original(path, options)
  })
  await enterApp('/jobs/42')
  await screen.findByRole('alert')
  expect(screen.getByRole('region', { name: 'Outcome' }).textContent).toContain('"sum": 10')
  failed = false
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByRole('article', { name: 'Attempt 1' })
})

test('shows an empty attempt page with a way back', async () => {
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (path, options) => String(path).includes('/attempts?') ? response([]) : original(path, options))
  await enterApp('/jobs/42/attempts?offset=10')
  await screen.findByText('No more execution attempts on this page.')
  expect((screen.getByRole('button', { name: 'Previous attempts' }) as HTMLButtonElement).disabled).toBe(false)
  expect((screen.getByRole('button', { name: 'Next attempts' }) as HTMLButtonElement).disabled).toBe(true)
})

test.each(['SUCCEEDED', 'FAILED'])('polls pending/running jobs and history, fetches final attempt, then stops for %s', async (terminalStatus) => {
  vi.useFakeTimers()
  localStorage.setItem(storageKey, token())
  window.history.replaceState(null, '', '/jobs/42')
  let status = 'PENDING'
  fetchMock.mockImplementation(async (path) => {
    if (path === '/api/users/me/') return response(user)
    const result = status === 'SUCCEEDED' ? { sum: 10 } : null
    const error = status === 'FAILED' ? { message: 'Invalid numbers' } : null
    if (path === '/api/jobs/42') return response({ ...job, status, result, error })
    return response(status === 'PENDING' ? [] : [{ ...attempt, status, result, error }])
  })
  await act(async () => { render(<App />) })
  await act(async () => { await vi.advanceTimersByTimeAsync(10) })
  expect(screen.getByRole('status').textContent).toBe('Pending')
  expect(screen.getByText('No execution attempts yet.')).toBeTruthy()
  status = 'RUNNING'
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.getByRole('status').textContent).toBe('Running')
  expect(screen.getByRole('article', { name: 'Attempt 1' }).textContent).toContain('Running')
  status = terminalStatus
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  const expected = status === 'SUCCEEDED' ? '"sum": 10' : 'Invalid numbers'
  expect(screen.getByRole('region', { name: 'Outcome' }).textContent).toContain(expected)
  expect(screen.getByRole('article', { name: 'Attempt 1' }).textContent).toContain(expected)
  const calls = fetchMock.mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(15_000) })
  expect(fetchMock).toHaveBeenCalledTimes(calls)
  expect(fetchMock.mock.calls.slice(1).map(([path]) => path)).toEqual(Array.from({ length: 3 }, () => ['/api/jobs/42', '/api/jobs/42/attempts?limit=1&offset=0']).flat())
})

test('pauses polling in a hidden tab, resumes when visible, and cancels on navigation', async () => {
  vi.useFakeTimers()
  localStorage.setItem(storageKey, token())
  window.history.replaceState(null, '', '/jobs/42')
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (path, options) => path === '/api/jobs/42'
    ? response({ ...job, status: 'RUNNING', result: null }) : original(path, options))
  await act(async () => { render(<App />) })
  await act(async () => { await vi.advanceTimersByTimeAsync(10) })
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  fireEvent(window, new Event('visibilitychange'))
  const calls = fetchMock.mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(9000) })
  expect(fetchMock).toHaveBeenCalledTimes(calls)
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  await act(async () => { fireEvent(window, new Event('visibilitychange')); await vi.advanceTimersByTimeAsync(3000) })
  expect(fetchMock.mock.calls.length).toBeGreaterThan(calls)
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  const signal = fetchMock.mock.calls.at(-1)?.[1]?.signal
  fireEvent.click(screen.getByRole('link', { name: 'Workers' }))
  expect(signal?.aborted).toBe(true)
  await act(async () => { resolve(response(job)); await vi.advanceTimersByTimeAsync(10) })
  expect(window.location.pathname).toBe('/workers')
  const afterNavigation = fetchMock.mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(6000) })
  expect(fetchMock).toHaveBeenCalledTimes(afterNavigation)
  vi.restoreAllMocks()
})

test('discards cached job data on logout before another account signs in', async () => {
  await enterApp('/jobs/42')
  await screen.findByRole('region', { name: 'Job overview' })
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  await screen.findByRole('heading', { name: 'Sign in' })
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (path, options) => path === '/api/users/me/'
    ? response({ ...user, id: 888, username: 'another-user' }) : original(path, options))
  fillLogin()
  await screen.findByRole('heading', { name: 'Job unavailable' })
  expect(screen.queryByRole('region', { name: 'Outcome' })).toBeNull()
  expect(document.body.textContent).not.toContain('demo-user (you)')
})

// Exercise the authenticated request boundary independently of feature screens.
function SessionProbe() {
  const { user: currentUser, expired, login, logout, request } = useAuth()
  return <>
    <span>{currentUser ? 'Authenticated' : expired ? 'Expired' : 'Signed out'}</span>
    <button onClick={() => { void login(user.username, 'Example1@', new AbortController().signal) }}>Authenticate</button>
    <button onClick={() => { void request('/jobs').catch(() => {}) }}>Load data</button>
    <button onClick={logout}>End session</button>
  </>
}

test('authenticated requests attach the token and remove the session on a backend 401', async () => {
  render(<AuthProvider><SessionProbe /></AuthProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Authenticate' }))
  await screen.findByText('Authenticated')
  fetchMock.mockResolvedValueOnce(response({ detail: 'Could not validate credentials' }, 401))
  fireEvent.click(screen.getByRole('button', { name: 'Load data' }))
  expect(await screen.findByText('Expired')).toBeTruthy()
  expect(localStorage.getItem(storageKey)).toBeNull()
  expect(new Headers(fetchMock.mock.calls[2][1]?.headers).get('Authorization')).toMatch(/^Bearer /)
  expect(fetchMock.mock.calls[2][1]?.signal?.aborted).toBe(true)
})

test('logout aborts in-flight authenticated requests and removes credentials', async () => {
  render(<AuthProvider><SessionProbe /></AuthProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Authenticate' }))
  await screen.findByText('Authenticated')
  let reject!: (reason: unknown) => void
  fetchMock.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
  fireEvent.click(screen.getByRole('button', { name: 'Load data' }))
  const signal = fetchMock.mock.calls[2][1]?.signal
  fireEvent.click(screen.getByRole('button', { name: 'End session' }))
  expect(screen.getByText('Signed out')).toBeTruthy()
  expect(signal?.aborted).toBe(true)
  await act(async () => { reject(new DOMException('Aborted', 'AbortError')) })
})
