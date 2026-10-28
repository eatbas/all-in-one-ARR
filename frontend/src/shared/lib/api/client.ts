/** Error raised when the backend returns a non-2xx response. */
export class ApiError extends Error {
  readonly status: number
  /**
   * The parsed `detail` of a JSON error body (for example FastAPI's 422
   * validation array), or `undefined` when the body had none.
   */
  readonly detail: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

/**
 * Build the error for a non-2xx response, preferring the backend's
 * `{ "detail": "..." }` body (FastAPI's convention) so the surfaced error carries
 * the server's reason. Falls back to a generic status message when the body is
 * empty, not JSON, or carries no string detail (e.g. a 422 validation array);
 * the parsed detail is kept on the error either way.
 */
async function responseError(
  input: string,
  response: Response,
): Promise<ApiError> {
  let detail: unknown
  try {
    detail = ((await response.json()) as { detail?: unknown }).detail
  } catch {
    // Empty or non-JSON body: fall through to the generic status message.
  }
  const message =
    typeof detail === "string"
      ? detail
      : `Request to ${input} failed with status ${response.status}`
  return new ApiError(response.status, message, detail)
}

export async function request<T>(
  input: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, {
    ...init,
    // Spread `init` first so caller headers (e.g. Content-Type on POST) are
    // merged into — not over — the default Accept header.
    headers: { Accept: "application/json", ...init?.headers },
  })

  if (!response.ok) {
    throw await responseError(input, response)
  }

  // 202/204 responses may carry an empty body; guard against that.
  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export async function postJson<T>(input: string, body: unknown): Promise<T> {
  return request<T>(input, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}
