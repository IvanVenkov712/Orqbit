// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { StrictMode } from 'react'
import App from '../App'
import { AuthProvider, useAuth } from '../auth'
import {
  user, fetchMock, storageKey, token, response, fillLogin, enterApp, fillRegistration, setupAppTests,
} from './app-test-utils'

setupAppTests()

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
  await screen.findByRole('region', { name: 'Worker metadata' })
  const accessToken = localStorage.getItem(storageKey)
  cleanup()
  let resolve!: (value: Response) => void
  fetchMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  render(<App />)
  expect(screen.getByRole('status').textContent).toBe('Restoring your session…')
  expect(screen.queryByRole('heading', { level: 1, name: 'Sign in' })).toBeNull()
  expect(screen.queryByText('Planned screen')).toBeNull()
  expect(window.location.pathname + window.location.search + window.location.hash).toBe(path)
  expect(fetchMock.mock.calls.at(-1)?.[0]).toBe('/api/users/me/')
  expect(new Headers(fetchMock.mock.calls.at(-1)?.[1]?.headers).get('Authorization')).toBe(`Bearer ${accessToken}`)
  await act(async () => { resolve(response({ ...user, full_name: 'Updated Name' })) })
  expect(await screen.findByRole('heading', { level: 1, name: 'Worker details' })).toBeTruthy()
  expect(screen.getByRole('group', { name: 'Current user' }).textContent).toContain('Updated Name')
  await screen.findByRole('region', { name: 'Worker metadata' })
  expect(fetchMock.mock.calls.filter(([path]) => path === '/api/users/me/')).toHaveLength(2)
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
  await screen.findByRole('region', { name: 'Worker metadata' })
  expect(fetchMock.mock.calls.filter(([path]) => path === '/api/users/me/')).toHaveLength(2)
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
