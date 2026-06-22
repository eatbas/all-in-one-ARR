/**
 * Shared test helpers that fabricate the minimal slice of TanStack Query's
 * result objects that components actually read, so mocked query/mutation hooks
 * do not each re-declare an `as unknown as ReturnType<…>` cast.
 */
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query"

/** A `useQuery`-shaped result carrying only `data` and `isLoading`. */
export function queryResult<T>(
  data: T | undefined,
  isLoading = false,
): UseQueryResult<T> {
  return { data, isLoading } as unknown as UseQueryResult<T>
}

/** A `useMutation`-shaped result carrying `mutate`, `isPending`, and `data`. */
export function mutationResult<TData, TVariables>(
  mutate: (variables: TVariables) => void,
  isPending = false,
  data?: TData,
): UseMutationResult<TData, Error, TVariables> {
  return { mutate, isPending, data } as unknown as UseMutationResult<
    TData,
    Error,
    TVariables
  >
}
