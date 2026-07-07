/** Error raised when the backend returns a non-2xx response. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

/**
 * Build the message for a non-2xx response, preferring the backend's
 * `{ "detail": "..." }` body (FastAPI's convention) so the surfaced error carries
 * the server's reason. Falls back to a generic status message when the body is
 * empty, not JSON, or carries no string detail (e.g. a 422 validation array).
 */
async function errorMessage(
  input: string,
  response: Response,
): Promise<string> {
  try {
    const { detail } = (await response.json()) as { detail?: unknown }
    if (typeof detail === "string") {
      return detail
    }
  } catch {
    // Empty or non-JSON body: fall through to the generic status message.
  }
  return `Request to ${input} failed with status ${response.status}`
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
    throw new ApiError(response.status, await errorMessage(input, response))
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
