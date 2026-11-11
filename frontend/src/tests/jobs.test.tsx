// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import App from '../App'
import {
  user, fetchMock, storageKey, job, attempt, token, response, fillLogin, enterApp, mockApi, setupAppTests,
} from './app-test-utils'

setupAppTests()

test('lists the current user’s jobs with owner, type, status, readable dates, and links to details', async () => {
  mockApi(async (path) => String(path).startsWith('/api/jobs?')
    ? response([{ ...job, status: 'PENDING' }, { ...job, id: 43, job_type: 'generate_report', status: 'PENDING' }, { ...job, id: 44, status: 'PENDING', user_id: 999 }, { ...job, id: 45, status: 'FAILED' }])
    : undefined)
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
  const page = [
    { ...job, id: 10, status: 'PENDING', updated_at: '2026-11-10T10:00:00Z' },
    { ...job, id: 20, status: 'PENDING', updated_at: '2026-11-10T08:00:00Z' },
    { ...job, id: 30, status: 'RUNNING', updated_at: '2026-11-10T09:00:00Z' },
    { ...job, id: 40, status: 'SUCCEEDED', updated_at: '2026-11-10T11:00:00Z' },
    { ...job, id: 50, status: 'SUCCEEDED', updated_at: '2026-11-10T07:00:00Z' },
    { ...job, id: 60, status: 'FAILED', updated_at: '2026-11-10T12:00:00Z' },
  ]
  mockApi(async (path) => String(path).startsWith('/api/jobs?')
    ? response(page.filter((job) => job.status === new URL(String(path), 'http://localhost').searchParams.get('status')))
    : undefined)
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
  mockApi(async (path) => String(path).startsWith('/api/jobs?') ? response([]) : undefined)
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
  mockApi(async (path) => {
    if (String(path).startsWith('/api/jobs?')) {
      const query = new URL(String(path), 'http://localhost').searchParams
      expect(query.get('owner_id')).toBe(String(user.id))
      expect(query.get('status')).toBe('FAILED')
      return response(query.get('offset') === '0' ? Array.from({ length: 20 }, (_, i) => ({ ...job, id: i + 1, status: 'FAILED' })) : [])
    }
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
  mockApi(async (path) => {
    if (String(path).includes('/attempts?')) {
      const limit = new URL(String(path), 'http://localhost').searchParams.get('limit')
      const attempts = [{ ...attempt, id: 20, attempt_number: 2 }, attempt]
      return response(limit === '1' ? attempts.slice(0, 1) : attempts)
    }
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
  mockApi(async (path) => String(path).includes('/attempts?') ? response([]) : undefined)
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
  mockApi(async (path) => {
    if (String(path).includes('/attempts?')) {
      const offset = Number(new URL(String(path), 'http://localhost').searchParams.get('offset'))
      return response(offset === 0 ? Array.from({ length: 10 }, (_, i) => ({ ...attempt, id: i + 2, attempt_number: 11 - i })) : [attempt])
    }
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
  let failed = true
  mockApi(async (path) => {
    if (String(path).includes('/attempts?') && failed) return response({}, 503)
  })
  await enterApp('/jobs/42')
  await screen.findByRole('alert')
  expect(screen.getByRole('region', { name: 'Outcome' }).textContent).toContain('"sum": 10')
  failed = false
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByRole('article', { name: 'Attempt 1' })
})

test('shows an empty attempt page with a way back', async () => {
  mockApi(async (path) => String(path).includes('/attempts?') ? response([]) : undefined)
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
  mockApi(async (path) => path === '/api/jobs/42'
    ? response({ ...job, status: 'RUNNING', result: null }) : undefined)
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
  mockApi(async (path) => path === '/api/users/me/'
    ? response({ ...user, id: 888, username: 'another-user' }) : undefined)
  fillLogin()
  await screen.findByRole('heading', { name: 'Job unavailable' })
  expect(screen.queryByRole('region', { name: 'Outcome' })).toBeNull()
  expect(document.body.textContent).not.toContain('demo-user (you)')
})
