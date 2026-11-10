// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App'
import { AuthProvider, useAuth } from './auth'

const user = { id: 7, username: 'demo-user', email: 'demo@example.com', full_name: 'Demo User', active: true, role: 'REGULAR' }
const fetchMock = vi.fn<typeof fetch>()

function token(expiresAt = Date.now() + 30 * 60_000) {
  return `header.${btoa(JSON.stringify({ sub: user.username, exp: Math.floor(expiresAt / 1000) }))}.signature`
}

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
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
  expect(window.localStorage.length).toBe(0)
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
])('restores %s after login and keeps its placeholder explicit', async (path, title, activeLink) => {
  await enterApp(path)
  expect(screen.getByRole('heading', { level: 1, name: title })).toBeTruthy()
  expect(screen.getByText('Planned screen')).toBeTruthy()
  expect(screen.getByText('You are signed in. Live job and worker data is not connected yet.')).toBeTruthy()
  expect(screen.getByRole('link', { name: activeLink }).getAttribute('aria-current')).toBe('page')
})

test('signs out and prevents browser back from reopening a protected screen', async () => {
  await enterApp()
  fireEvent.click(screen.getByRole('link', { name: 'Workers' }))
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(screen.queryByText('Demo User (@demo-user)')).toBeNull()
  await act(async () => { window.history.back() })
  await waitFor(() => expect(window.location.pathname).toBe('/login'))
  expect(screen.queryByText('Planned screen')).toBeNull()
})

test('requires login again after remounting the application (page refresh)', async () => {
  await enterApp()
  cleanup()
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledTimes(2)
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

test('links to the submission placeholder after authentication', async () => {
  await enterApp()
  fireEvent.click(screen.getByRole('link', { name: 'Preview job submission' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Submit a job' })).toBeTruthy()
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
