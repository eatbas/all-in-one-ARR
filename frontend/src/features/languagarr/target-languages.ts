import { describeLanguages } from "@/shared/lib/api"
import { useLanguagarrLanguages } from "@/shared/lib/queries"

/**
 * Target languages as prose for UI copy ("English or Turkish"). Names come from
 * the language catalogue; while it loads, the codes are shown upper-cased.
 */
export function useLanguagesLabel(codes: readonly string[]): string {
  const { data } = useLanguagarrLanguages()
  return describeLanguages(codes, data)
}
