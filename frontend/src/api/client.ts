export type FieldValidationError = {
  loc: (string | number)[]
  msg: string
  type: string
}

export class ApiError extends Error {
  readonly status: number | null
  readonly fieldErrors: FieldValidationError[]

  constructor(message: string, status: number | null, fieldErrors: FieldValidationError[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

type ApiRequestOptions = Omit<RequestInit, 'body'> & { token?: string } & (
  | { json?: unknown; form?: never }
  | { json?: never; form: URLSearchParams }
)

function httpError(status: number, payload: unknown): ApiError {
  // Server failures may contain internal details, even when they are JSON.
  if (status >= 500) {
    return new ApiError('Orqbit is temporarily unavailable. Please try again later.', status)
  }

  const detail = payload && typeof payload === 'object' && 'detail' in payload
    ? payload.detail
    : undefined

  if (typeof detail === 'string' && detail.trim()) {
    return new ApiError(detail, status)
  }

  if (Array.isArray(detail)) {
    const fieldErrors: FieldValidationError[] = detail.flatMap((error: unknown) => {
      if (!error || typeof error !== 'object' || !('loc' in error)
        || !Array.isArray(error.loc)
        || !error.loc.every((part: unknown) => typeof part === 'string' || typeof part === 'number')
        || !('msg' in error) || typeof error.msg !== 'string'
        || !('type' in error) || typeof error.type !== 'string') {
        return []
      }
      // Copy only the public validation fields; never retain input or ctx.
      return [{ loc: [...error.loc], msg: error.msg, type: error.type }]
    })

    if (fieldErrors.length) {
      const message = fieldErrors.map(({ loc, msg }) => {
        const field = loc.filter((part, index) => index !== 0 || !['body', 'query', 'path', 'header'].includes(String(part)))
          .join('.')
        return field ? `${field}: ${msg}` : msg
      }).join('; ')
      return new ApiError(message, status, fieldErrors)
    }
  }

  return new ApiError(`Request failed (HTTP ${status}). Please try again.`, status)
}

/** Paths are relative to /api (for example, /users/me/); T describes the JSON response.
 * Use T = void for an empty response. Tokens are supplied per request, never stored here.
 */
export async function apiRequest<T = unknown>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { token, json, form, headers: suppliedHeaders, ...requestOptions } = options
  const headers = new Headers(suppliedHeaders)
  headers.set('Accept', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let body: BodyInit | undefined
  if (form !== undefined) {
    body = form
    headers.set('Content-Type', 'application/x-www-form-urlencoded;charset=UTF-8')
  } else if (json !== undefined) {
    body = JSON.stringify(json)
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  let responseText: string
  try {
    response = await fetch(`/api${path}`, { ...requestOptions, headers, body })
    responseText = await response.text()
  } catch {
    if (requestOptions.signal?.aborted) {
      throw new DOMException('The request was cancelled.', 'AbortError')
    }
    // Do not attach the original exception, request, headers, or body.
    throw new ApiError('Unable to reach Orqbit. Check your connection and try again.', null)
  }

  let payload: unknown
  if (responseText.trim()) {
    try {
      payload = JSON.parse(responseText)
    } catch {
      if (response.ok) {
        throw new ApiError('Orqbit returned an invalid response. Please try again.', response.status)
      }
    }
  }

  if (!response.ok) throw httpError(response.status, payload)
  return payload as T
}
