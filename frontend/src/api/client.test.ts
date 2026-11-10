import { afterEach, expect, test, vi } from 'vitest'
import { ApiError, apiRequest } from './client'

const fetchMock = vi.fn<typeof fetch>()

afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

function respond(body: unknown, status = 200) {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockImplementation(async () => new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

test('prefixes /api, preserves slashes and query parameters, and parses JSON', async () => {
  respond([{ id: 7 }])

  expect(await apiRequest('/jobs?limit=1&offset=2')).toEqual([{ id: 7 }])
  expect(fetchMock.mock.calls[0][0]).toBe('/api/jobs?limit=1&offset=2')
  const options = fetchMock.mock.calls[0][1]!
  expect(new Headers(options.headers).get('Accept')).toBe('application/json')
  expect(new Headers(options.headers).has('Authorization')).toBe(false)
  expect(new Headers(options.headers).has('Content-Type')).toBe(false)
  expect(options.body).toBeUndefined()

  await apiRequest('/users/me/')
  expect(fetchMock.mock.calls[1][0]).toBe('/api/users/me/')
})

test('sends JSON, a bearer token, and caller headers without mutating them', async () => {
  respond({ id: 7 })
  const headers = new Headers({ 'Idempotency-Key': 'submission-1' })

  await apiRequest('/jobs/', {
    method: 'POST', token: 'user-token', headers, json: { params: { numbers: [2, 3] } },
  })

  const options = fetchMock.mock.calls[0][1]!
  expect(options.method).toBe('POST')
  expect(options.body).toBe('{"params":{"numbers":[2,3]}}')
  expect(new Headers(options.headers).get('Content-Type')).toBe('application/json')
  expect(new Headers(options.headers).get('Authorization')).toBe('Bearer user-token')
  expect(new Headers(options.headers).get('Idempotency-Key')).toBe('submission-1')
  expect(headers.has('Authorization')).toBe(false)

  await apiRequest('/auth/register', { method: 'POST', json: null })
  expect(fetchMock.mock.calls[1][1]!.body).toBe('null')
  await apiRequest('/jobs')
  expect(new Headers(fetchMock.mock.calls[2][1]!.headers).has('Authorization')).toBe(false)
})

test('sends URL-encoded login fields with the correct content type', async () => {
  respond({ access_token: 'token', token_type: 'bearer' })
  const form = new URLSearchParams({ username: 'test_user', password: 'A+b&c#1' })

  await apiRequest('/auth/login', {
    method: 'POST', form, headers: { 'Content-Type': 'application/json' },
  })

  const options = fetchMock.mock.calls[0][1]!
  expect(String(options.body)).toBe('username=test_user&password=A%2Bb%26c%231')
  expect(new Headers(options.headers).get('Content-Type')).toBe('application/x-www-form-urlencoded;charset=UTF-8')
})

test.each([200, 204])('handles an empty %s response', async (status) => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockResolvedValue(new Response(null, { status }))

  expect(await apiRequest<void>('/jobs')).toBeUndefined()
})

test.each([
  [401, 'Incorrect username or password'],
  [404, 'Job not found'],
  [409, 'Worker name already exists'],
])('preserves public string errors and HTTP status %s', async (status, detail) => {
  respond({ detail }, status)

  await expect(apiRequest('/jobs')).rejects.toMatchObject({
    name: 'ApiError', message: detail, status, fieldErrors: [],
  })
})

test('exposes field paths and messages, discarding rejected input and context', async () => {
  respond({ detail: [
    {
      loc: ['body', 'password'], msg: 'String should match pattern', type: 'string_pattern_mismatch',
      input: 'private-password', ctx: { internal: 'private-context' },
    },
    { loc: ['body', 'params', 'numbers', 0], msg: 'Input should be a valid number', type: 'float_parsing' },
    { loc: ['query', 'limit'], msg: 'Input should be greater than 0', type: 'greater_than' },
  ] }, 422)

  const error = await apiRequest('/jobs').catch((error: unknown) => error)
  expect(error).toBeInstanceOf(ApiError)
  expect(error).toMatchObject({
    status: 422,
    message: 'password: String should match pattern; params.numbers.0: Input should be a valid number; limit: Input should be greater than 0',
    fieldErrors: [
      { loc: ['body', 'password'], msg: 'String should match pattern', type: 'string_pattern_mismatch' },
      { loc: ['body', 'params', 'numbers', 0], msg: 'Input should be a valid number', type: 'float_parsing' },
      { loc: ['query', 'limit'], msg: 'Input should be greater than 0', type: 'greater_than' },
    ],
  })
  expect(JSON.stringify(error)).not.toContain('private-')
})

test.each([null, {}, { detail: [] }, { detail: [null, { loc: 'password', msg: 'bad' }] }])(
  'provides a fallback for an unrecognized error response: %j', async (body) => {
    respond(body, 400)
    await expect(apiRequest('/jobs')).rejects.toMatchObject({
      status: 400, message: 'Request failed (HTTP 400). Please try again.', fieldErrors: [],
    })
  },
)

test.each([
  [500, '{"detail":"private database credentials"}'],
  [502, '<html>private proxy details</html>'],
  [400, 'private unstructured error'],
  [200, 'private malformed JSON'],
])('does not expose raw internal or invalid responses (%s)', async (status, body) => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockResolvedValue(new Response(body, { status }))

  const error = await apiRequest('/jobs').catch((error: unknown) => error)
  expect(error).toBeInstanceOf(ApiError)
  expect(error).toMatchObject({ status })
  expect(String(error)).not.toContain('private')
  expect(JSON.stringify(error)).not.toContain('private')
})

test('sanitizes network failures without retaining credentials or the original exception', async () => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockRejectedValue(new TypeError('private network diagnostics'))

  const error = await apiRequest('/auth/login', {
    method: 'POST', token: 'private-token',
    form: new URLSearchParams({ username: 'test_user', password: 'private-password' }),
  }).catch((error: unknown) => error)

  expect(error).toBeInstanceOf(ApiError)
  expect(error).toMatchObject({
    status: null, message: 'Unable to reach Orqbit. Check your connection and try again.',
  })
  expect(error).not.toHaveProperty('cause')
  expect(JSON.stringify(error)).not.toContain('private')
})

test('sanitizes failures while reading the response body', async () => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockResolvedValue({ text: () => Promise.reject(new Error('private stream error')) } as Response)

  await expect(apiRequest('/jobs')).rejects.toMatchObject({ name: 'ApiError', status: null })
})

test('forwards cancellation and preserves a safe AbortError', async () => {
  vi.stubGlobal('fetch', fetchMock)
  const controller = new AbortController()
  controller.abort('private abort reason')
  fetchMock.mockRejectedValue(controller.signal.reason)

  const error = await apiRequest('/jobs', { signal: controller.signal }).catch((error: unknown) => error)

  expect(fetchMock.mock.calls[0][1]!.signal).toBe(controller.signal)
  expect(error).toMatchObject({ name: 'AbortError', message: 'The request was cancelled.' })
  expect(String(error)).not.toContain('private')
})
