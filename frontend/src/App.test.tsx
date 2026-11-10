// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { StrictMode } from 'react'
import App from './App'
import { AuthProvider, useAuth } from './auth'
import orqbitIcon from './assets/orqbit-icon.svg'

const user = { id: 7, username: 'demo-user', email: 'demo@example.com', full_name: 'Demo User', active: true, role: 'REGULAR' }
const fetchMock = vi.fn<typeof fetch>()
const storageKey = 'orqbit.access_token'

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
    throw new Error('Unexpected request')
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
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

test.each(['/jobs', '/jobs/new', '/jobs/42', '/workers', '/workers/17'])(
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
  expect(screen.getByRole('group', { name: 'Current user' }).textContent).toContain('Demo User (@demo-user)')
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
  ['/workers', 'Workers', 'Workers'],
  ['/workers/17', 'Worker details', 'Workers'],
])('restores %s after login and highlights its section', async (path, title, activeLink) => {
  await enterApp(path)
  expect(screen.getByRole('heading', { level: 1, name: title })).toBeTruthy()
  if (path === '/jobs/new') {
    expect(screen.queryByText('Planned screen')).toBeNull()
    expect(screen.getByRole('form', { name: 'Submit a job' })).toBeTruthy()
  } else {
    expect(screen.getByText('Planned screen')).toBeTruthy()
    expect(screen.getByText('You are signed in. This screen does not load live data yet.')).toBeTruthy()
  }
  expect(screen.getByRole('link', { name: activeLink }).getAttribute('aria-current')).toBe('page')
})

test('signs out and prevents browser back from reopening a protected screen', async () => {
  await enterApp()
  fireEvent.click(screen.getByRole('link', { name: 'Workers' }))
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(screen.queryByText('Demo User (@demo-user)')).toBeNull()
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
  for (const call of fetchMock.mock.calls.slice(3)) {
    expect(call[1]?.body).toBe(fetchMock.mock.calls[2][1]?.body)
    expect(new Headers(call[1]?.headers).get('Idempotency-Key')).toBe(new Headers(fetchMock.mock.calls[2][1]?.headers).get('Idempotency-Key'))
  }
  expect(fetchMock).toHaveBeenCalledTimes(5)
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

// Exercise the authenticated request boundary before feature data screens exist.
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
