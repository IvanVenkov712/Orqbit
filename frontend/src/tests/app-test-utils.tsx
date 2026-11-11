import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, vi } from 'vitest'
import App from '../App'

export const user = { id: 7, username: 'demo-user', email: 'demo@example.com', full_name: 'Demo User', active: true, role: 'REGULAR' }
export const fetchMock = vi.fn<typeof fetch>()
export const storageKey = 'orqbit.access_token'
export const worker = {
  id: 17, user_id: user.id, name: 'numbers-worker', active: true,
  supported_types: ['add_numbers', 'sum'], permission_policy: 'PRIVATE', permitted_user_ids: [],
}
export const job = {
  id: 42, user_id: user.id, job_type: 'add_numbers', status: 'SUCCEEDED',
  params: { numbers: [2, 3, 5] }, result: { sum: 10 }, error: null,
  created_at: '2026-11-10T08:00:00Z', updated_at: '2026-11-10T09:30:00Z',
}
export const attempt = {
  id: 19, job_id: job.id, worker_id: 12, job_type: job.job_type,
  attempt_number: 1, status: 'SUCCEEDED', params: job.params,
  result: job.result, error: null,
  created_at: '2026-11-10T08:00:00Z', updated_at: '2026-11-10T08:00:01Z',
}

export function token(expiresAt = Date.now() + 30 * 60_000) {
  return `header.${btoa(JSON.stringify({ sub: user.username, exp: Math.floor(expiresAt / 1000) }))}.signature`
}

export function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export function setupAppTests() {
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
      if (String(path).startsWith('/api/workers?')) return response([worker])
      if (/^\/api\/workers\/\d+$/.test(String(path))) return response(worker)
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
}

export function fillLogin() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: user.username } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Example1@' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

export async function enterApp(path = '/jobs') {
  window.history.replaceState(null, '', path)
  render(<App />)
  fillLogin()
  await screen.findByRole('button', { name: 'Sign out' })
  await waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).not.toBe('Sign in'))
}

export function fillRegistration() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: user.username } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: user.email } })
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: user.full_name } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Example1@' } })
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
}

export function addParameter(name: string | undefined, value: unknown, path = 'Parameters', index = 1) {
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

export function fillJob(params: Record<string, unknown> = { numbers: [2, 3, 5] }, jobType = 'add_numbers') {
  fireEvent.change(screen.getByLabelText('Job type'), { target: { value: jobType } })
  for (const button of screen.queryAllByRole('button', { name: /^Remove Parameters \d+$/ })) fireEvent.click(button)
  Object.entries(params).forEach(([name, value], i) => addParameter(name, value, 'Parameters', i + 1))
}

export function submitJob() {
  fireEvent.submit(screen.getByRole('form', { name: 'Submit a job' }))
}

export function fillWorkerRegistration(types = 'add_numbers\nsum\nadd_numbers') {
  fireEvent.change(screen.getByLabelText('Worker name'), { target: { value: worker.name } })
  fireEvent.change(screen.getByLabelText('Supported types'), { target: { value: types } })
  fireEvent.submit(screen.getByRole('form', { name: 'Register a worker' }))
}

// Return undefined for requests that should use the existing mock response.
export function mockApi(handler: (...args: Parameters<typeof fetch>) => Promise<Response | undefined>) {
  const original = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (...args) => {
    const result = await handler(...args)
    return result ?? original(...args)
  })
}
