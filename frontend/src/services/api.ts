export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}

type TokenSource = () => Promise<string | null>
let tokenSource: TokenSource | null = null

/** Supplies the signed-in user's Clerk session token for every API request. */
export function setTokenSource(source: TokenSource | null) { tokenSource = source }

async function authorize(headers: Record<string, string> = {}): Promise<Record<string, string>> {
  const token = tokenSource ? await tokenSource() : null
  return token ? { ...headers, Authorization: `Bearer ${token}` } : headers
}

async function failure(response: Response, method: string): Promise<never> {
  const data = await response.json().catch(() => null)
  const detail = typeof data?.detail === 'string' ? data.detail : null
  throw new ApiError(detail ?? `Could not ${method === 'GET' ? 'load' : 'save'} this. Please try again. (${response.status})`, response.status)
}

export async function api<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    signal,
    headers: await authorize(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) return failure(response, method)
  return response.status === 204 ? undefined as T : response.json()
}

/** Sends a file's raw bytes (e.g. a CSV) so the server can enforce size limits while reading. */
export async function apiUpload<T>(path: string, file: File, contentType = 'text/csv'): Promise<T> {
  const response = await fetch(`/api${path}`, { method: 'POST', headers: await authorize({ 'Content-Type': contentType }), body: file })
  if (!response.ok) return failure(response, 'POST')
  return response.json()
}
