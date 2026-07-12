/**
 * Exception-safe access to `localStorage` for persisted UI preferences.
 *
 * Browser privacy settings, disabled third-party storage, and quota errors can
 * all throw when `localStorage` is referenced or when `getItem`/`setItem` are
 * called. These helpers absorb every failure: reads return the explicit default,
 * and writes silently no-op.
 */

function getLocalStorage(): Storage | undefined {
  try {
    if (typeof localStorage === "undefined") return undefined
    return localStorage
  } catch {
    return undefined
  }
}

/**
 * Read a string preference from `localStorage`, parse it, and fall back to the
 * supplied default when storage is unavailable, the key is absent, or parsing
 * fails. The parser may return `null`/`undefined` to signal an invalid value.
 */
export function readStoredItem<T>(
  key: string,
  defaultValue: T,
  parse: (raw: string) => T | null | undefined,
): T {
  const storage = getLocalStorage()
  if (!storage) return defaultValue
  try {
    const raw = storage.getItem(key)
    if (raw === null) return defaultValue
    const parsed = parse(raw)
    return parsed === null || parsed === undefined ? defaultValue : parsed
  } catch {
    return defaultValue
  }
}

/**
 * Write a preference to `localStorage`. Serialises with `String` by default.
 * Does nothing when storage is unavailable or `setItem` throws (for example a
 * quota error).
 */
export function writeStoredItem<T>(
  key: string,
  value: T,
  serialize: (value: T) => string = String,
): void {
  const storage = getLocalStorage()
  if (!storage) return
  try {
    storage.setItem(key, serialize(value))
  } catch {
    // Storage denied or quota exceeded — keep the UI working without the pref.
  }
}
