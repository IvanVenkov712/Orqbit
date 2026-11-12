// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import App from '../App'
import { enterApp, fetchMock, mockApi, response, setupAppTests, user } from './app-test-utils'

setupAppTests()

const producer = { id: 10, name: 'test-producer', active: true, user_id: user.id, owner_username: user.username }
beforeEach(() => {
  mockApi(async (path) => String(path).startsWith('/api/producers?') ? response([producer])
    : path === '/api/producers/10' || path === '/api/producers/by-name/test-producer' ? response(producer) : undefined)
})

function create(name = producer.name) {
  fireEvent.change(screen.getByLabelText('Producer name'), { target: { value: name } })
  fireEvent.submit(screen.getByRole('form', { name: 'Create a producer' }))
}

test.each(['/producers', '/producers/new', '/producers/10'])('protects direct entry to %s', (path) => {
  window.history.replaceState(null, '', path)
  render(<App />)
  expect(window.location.pathname).toBe('/login')
  expect(fetchMock).not.toHaveBeenCalled()
})

test.each([
  ['/producers', 'Producers'], ['/producers/new', 'Create a producer'], ['/producers/10', 'Producer details'],
])('restores %s after login and highlights Producers', async (path, heading) => {
  await enterApp(path)
  expect(screen.getByRole('heading', { level: 1, name: heading })).toBeTruthy()
  expect(window.location.pathname).toBe(path)
  expect(screen.getByRole('link', { name: 'Producers' }).getAttribute('aria-current')).toBe('page')
})

test('lists producer metadata, hides credentials and links to details', async () => {
  mockApi(async (path) => String(path).startsWith('/api/producers?')
    ? response([{ ...producer, secret_api_key: 'never-display', secret_api_key_hash: 'never-display-hash' }]) : undefined)
  await enterApp('/producers')
  const table = await screen.findByRole('table', { name: 'Registered producers' })
  expect(table.textContent).toContain(user.username)
  expect(table.textContent).toContain('Active')
  expect(document.body.textContent).not.toContain('never-display')
  fireEvent.click(screen.getByRole('link', { name: producer.name }))
  expect((await screen.findByRole('region', { name: 'Producer metadata' })).textContent).toContain('#10')
  expect(screen.queryByLabelText('Producer API key')).toBeNull()
})

test('searches partial names, resets pagination and restores filters on back/forward and reload', async () => {
  await enterApp('/producers?offset=20')
  await screen.findByRole('table', { name: 'Registered producers' })
  fireEvent.change(screen.getByLabelText('Producer name or ID'), { target: { value: 'test_%' } })
  fireEvent.change(screen.getByLabelText('Producers per page'), { target: { value: '50' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Search producers' }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([path]) => String(path) === '/api/producers?limit=50&offset=0&query=test_%25')).toBe(true))
  expect(new URLSearchParams(window.location.search).has('offset')).toBe(false)
  await act(async () => { window.history.back() })
  await waitFor(() => expect((screen.getByLabelText('Producer name or ID') as HTMLInputElement).value).toBe(''))
  await act(async () => { window.history.forward() })
  await waitFor(() => expect((screen.getByLabelText('Producer name or ID') as HTMLInputElement).value).toBe('test_%'))
  cleanup()
  render(<App />)
  await screen.findByRole('table', { name: 'Registered producers' })
  expect((screen.getByLabelText('Producers per page') as HTMLSelectElement).value).toBe('50')
  fireEvent.click(screen.getByRole('link', { name: 'Clear filters' }))
  await waitFor(() => expect(window.location.search).toBe(''))
})

test.each([
  ['id', '10', '/api/producers/10'], ['name', producer.name, `/api/producers/by-name/${producer.name}`],
])('looks up a producer by %s using its exact API endpoint', async (lookup, value, endpoint) => {
  await enterApp('/producers')
  fireEvent.change(screen.getByLabelText('Search by'), { target: { value: lookup } })
  fireEvent.change(screen.getByLabelText('Producer name or ID'), { target: { value } })
  fireEvent.submit(screen.getByRole('form', { name: 'Search producers' }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([path]) => path === endpoint)).toBe(true))
  await screen.findByRole('link', { name: producer.name })
  expect(screen.queryByRole('navigation', { name: 'Producer pages' })).toBeNull()
})

test.each(['?lookup=id&query=0', '?lookup=id&query=9007199254740992', '?lookup=name&query=ab', '?query=abcdefghijklmnopq'])(
  'rejects invalid search parameters %s without an API request', async (query) => {
    await enterApp(`/producers${query}`)
    expect((await screen.findByRole('alert')).textContent).toContain('valid producer name or ID')
    expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith('/api/producers'))).toBe(false)
  },
)

test('paginates filtered producers, handles an empty next page and returns to the previous page', async () => {
  mockApi(async (path) => {
    if (!String(path).startsWith('/api/producers?')) return
    const search = new URL(String(path), 'http://localhost').searchParams
    return response(search.get('offset') === '0' ? Array.from({ length: 20 }, (_, index) => ({ ...producer, id: index + 1, name: `producer-${index}` })) : [])
  })
  await enterApp('/producers?query=test')
  fireEvent.click(await screen.findByRole('button', { name: 'Next producers' }))
  await screen.findByText('No more producers on this page.')
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/producers?limit=20&offset=20&query=test')).toBe(true)
  expect((screen.getByRole('button', { name: 'Next producers' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Previous producers' }))
  await screen.findByRole('link', { name: 'producer-0' })
})

test('offers retry after a list failure and shows an empty search result', async () => {
  let failed = true
  mockApi(async (path) => String(path).startsWith('/api/producers?') ? failed ? response({}, 503) : response([]) : undefined)
  await enterApp('/producers')
  expect((await screen.findByRole('alert')).textContent).toContain('temporarily unavailable')
  failed = false
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByRole('heading', { name: 'No producers found' })
})

test('creates with bearer authentication, copies the key and refreshes the list without retaining the key', async () => {
  let created = false
  mockApi(async (path) => {
    if (path === '/api/producers') { created = true; return response({ ...producer, secret_api_key: 'creation-secret' }) }
    if (String(path).startsWith('/api/producers?')) return response(created ? [producer] : [])
  })
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  await enterApp('/producers')
  await screen.findByRole('heading', { name: 'No producers found' })
  fireEvent.click(screen.getByRole('link', { name: 'Create a producer' }))
  create()
  expect((await screen.findByLabelText('Producer API key')).textContent).toBe('creation-secret')
  const [, options] = fetchMock.mock.calls.find(([path]) => path === '/api/producers')!
  expect(options?.method).toBe('POST')
  expect(JSON.parse(String(options?.body))).toEqual({ name: producer.name })
  expect(new Headers(options?.headers).get('Authorization')).toMatch(/^Bearer /)
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain('creation-secret')
  fireEvent.click(screen.getByRole('button', { name: 'Copy API key' }))
  await screen.findByText('API key copied. Save it securely.')
  expect(writeText).toHaveBeenCalledWith('creation-secret')
  fireEvent.click(screen.getByRole('link', { name: 'Back to Producers' }))
  await screen.findByRole('link', { name: producer.name })
  fireEvent.click(screen.getByRole('link', { name: 'Create a producer' }))
  expect(screen.queryByLabelText('Producer API key')).toBeNull()
  expect(fetchMock.mock.calls.filter(([path]) => path === '/api/producers')).toHaveLength(1)
})

test('discards a new key on reload and offers manual copying when the clipboard fails', async () => {
  mockApi(async (path) => path === '/api/producers' ? response({ ...producer, secret_api_key: 'temporary-secret' }) : undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } })
  await enterApp('/producers/new')
  create()
  await screen.findByLabelText('Producer API key')
  fireEvent.click(screen.getByRole('button', { name: 'Copy API key' }))
  expect((await screen.findByRole('status')).textContent).toContain('copy it manually')
  cleanup()
  render(<App />)
  await screen.findByRole('form', { name: 'Create a producer' })
  expect(document.body.textContent).not.toContain('temporary-secret')
  expect(fetchMock.mock.calls.filter(([path]) => path === '/api/producers')).toHaveLength(1)
})

test.each(['ab', 'invalid!', 'abcdefghijklmnopq'])('validates the name %s before creating', async (name) => {
  await enterApp('/producers/new')
  create(name)
  expect(screen.getByRole('alert').textContent).toContain('3–16')
  expect(screen.getByLabelText('Producer name').getAttribute('aria-invalid')).toBe('true')
  expect(fetchMock.mock.calls.some(([path]) => path === '/api/producers')).toBe(false)
})

test.each([409, 422])('shows a name error for HTTP %s and allows correction', async (status) => {
  mockApi(async (path, options) => path === '/api/producers'
    ? JSON.parse(String(options?.body)).name !== producer.name ? response({ ...producer, secret_api_key: 'new-key' })
      : status === 409 ? response({ detail: 'Producer name already exists' }, 409)
        : response({ detail: [{ loc: ['body', 'name'], msg: 'Invalid producer name', type: 'value_error' }] }, 422)
    : undefined)
  await enterApp('/producers/new')
  create()
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Producer name').getAttribute('aria-invalid')).toBe('true')
  create('another-producer')
  await screen.findByLabelText('Producer API key')
})

test('explains uncertain creation without automatically retrying', async () => {
  mockApi(async (path) => { if (path === '/api/producers') throw new Error('private diagnostics') })
  await enterApp('/producers/new')
  create()
  expect((await screen.findByRole('alert')).textContent).toContain('Unable to reach Orqbit')
  expect(screen.getByText(/producer may have been created/)).toBeTruthy()
  expect(document.body.textContent).not.toContain('private diagnostics')
  expect(fetchMock.mock.calls.filter(([path]) => path === '/api/producers')).toHaveLength(1)
})

test.each([
  ['Reissue API key', 'Confirm reissue'], ['Deactivate producer', 'Confirm deactivation'], ['Delete producer', 'Confirm deletion'],
])('requires confirmation for %s and allows cancellation', async (button, confirmation) => {
  await enterApp('/producers/10')
  fireEvent.click(await screen.findByRole('button', { name: button }))
  expect(screen.getByRole('button', { name: confirmation })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('region', { name: 'Confirm producer action' })).toBeNull()
  expect(fetchMock.mock.calls.filter(([, options]) => ['POST', 'DELETE'].includes(options?.method ?? '')).map(([path]) => path)).toEqual(['/api/auth/login'])
})

test.each([true, false])('reissues a key without changing active=%s and discards it on navigation', async (active) => {
  mockApi(async (path) => path === '/api/producers/10' ? response({ ...producer, active })
    : path === '/api/producers/10/api-key' ? response({ secret_api_key: 'replacement-secret' }) : undefined)
  await enterApp('/producers/10')
  fireEvent.click(await screen.findByRole('button', { name: 'Reissue API key' }))
  expect(screen.getByText(/old key will stop working immediately/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm reissue' }))
  expect((await screen.findByLabelText('Producer API key')).textContent).toBe('replacement-secret')
  expect(screen.getByRole('region', { name: 'Producer metadata' }).textContent).toContain(active ? 'Active' : 'Inactive')
  expect(fetchMock.mock.calls.find(([path]) => path === '/api/producers/10/api-key')![1]?.method).toBe('POST')
  fireEvent.click(screen.getByRole('link', { name: 'Back to Producers' }))
  fireEvent.click(await screen.findByRole('link', { name: producer.name }))
  await screen.findByRole('region', { name: 'Producer metadata' })
  expect(document.body.textContent).not.toContain('replacement-secret')
})

test('deactivates the producer, updates the list and disables further deactivation', async () => {
  let active = true
  mockApi(async (path) => {
    if (path === '/api/producers/10/deactivate') { active = false; return response({ ...producer, active }) }
    if (String(path).startsWith('/api/producers?')) return response([{ ...producer, active }])
  })
  await enterApp('/producers/10')
  fireEvent.click(await screen.findByRole('button', { name: 'Deactivate producer' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm deactivation' }))
  await screen.findByText('Producer deactivated. Existing jobs are preserved.')
  expect((screen.getByRole('button', { name: 'Deactivate producer' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText('Inactive')).toBeTruthy()
  fireEvent.click(screen.getByRole('link', { name: 'Back to Producers' }))
  await screen.findByText('Inactive')
})

test.each([false, true])('handles deletion with referenced jobs=%s', async (referenced) => {
  let deleted = false
  mockApi(async (path, options) => {
    if (path === '/api/producers/10' && options?.method === 'DELETE') {
      if (referenced) return response({ detail: 'Producer is referenced by jobs' }, 409)
      deleted = true
      return new Response(null, { status: 204 })
    }
    if (String(path).startsWith('/api/producers?')) return response(deleted ? [] : [producer])
  })
  await enterApp('/producers/10')
  fireEvent.click(await screen.findByRole('button', { name: 'Delete producer' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm deletion' }))
  if (referenced) {
    expect((await screen.findByRole('alert')).textContent).toContain('Deactivate it instead')
    expect(window.location.pathname).toBe('/producers/10')
    expect(screen.getByRole('button', { name: 'Deactivate producer' })).toBeTruthy()
  } else {
    await screen.findByRole('heading', { name: 'No producers found' })
    expect(window.location.pathname).toBe('/producers')
  }
})

test.each(['0', 'invalid', '9007199254740992', '404', '403'])('handles unavailable producer %s without management actions', async (id) => {
  mockApi(async (path) => path === `/api/producers/${id}` ? response({ detail: 'Producer not found' }, Number(id)) : undefined)
  await enterApp(`/producers/${id}`)
  await screen.findByRole('heading', { name: 'Producer unavailable' })
  expect(screen.queryByRole('button', { name: 'Reissue API key' })).toBeNull()
  if (!['403', '404'].includes(id)) expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith('/api/producers/'))).toBe(false)
})

test('explains an uncertain key reissue and allows refreshing details', async () => {
  mockApi(async (path) => { if (path === '/api/producers/10/api-key') throw new Error('network') })
  await enterApp('/producers/10')
  fireEvent.click(await screen.findByRole('button', { name: 'Reissue API key' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm reissue' }))
  await screen.findByRole('alert')
  expect(screen.getByText(/previous key may already be invalid/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh producer details' }))
  await waitFor(() => expect(fetchMock.mock.calls.filter(([path]) => path === '/api/producers/10')).toHaveLength(2))
  expect(fetchMock.mock.calls.filter(([path]) => path === '/api/producers/10/api-key')).toHaveLength(1)
})

test.each(['create', 'reissue'])('prevents duplicate %s requests and aborts on navigation', async (operation) => {
  const endpoint = operation === 'create' ? '/api/producers' : '/api/producers/10/api-key'
  let resolve!: (value: Response) => void
  mockApi(async (path) => path === endpoint ? new Promise((done) => { resolve = done }) : undefined)
  await enterApp(operation === 'create' ? '/producers/new' : '/producers/10')
  if (operation === 'create') { create(); create() }
  else {
    fireEvent.click(await screen.findByRole('button', { name: 'Reissue API key' }))
    const confirm = screen.getByRole('button', { name: 'Confirm reissue' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
  }
  expect(fetchMock.mock.calls.filter(([path]) => path === endpoint)).toHaveLength(1)
  const signal = fetchMock.mock.calls.find(([path]) => path === endpoint)![1]?.signal
  fireEvent.click(screen.getByRole('link', { name: 'Back to Producers' }))
  expect(signal?.aborted).toBe(true)
  await act(async () => { resolve(response({ ...producer, secret_api_key: 'late-secret' })) })
  expect(document.body.textContent).not.toContain('late-secret')
})
