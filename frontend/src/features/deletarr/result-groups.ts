import type { ResultGroup } from "@/features/deletarr/components/result-group-panel"
import type { DeletarrScanItem } from "@/shared/lib/api"

/** Group candidates by their owning movie or series folder. */
export function groupResults(items: DeletarrScanItem[]): ResultGroup[] {
  const grouped = new Map<string, ResultGroup>()
  for (const item of items) {
    const key = item.movie_folder_path ?? item.parent
    const existing = grouped.get(key)
    if (existing) {
      existing.items.push(item)
      if (existing.videos.length === 0 && item.videos_in_folder.length > 0) {
        existing.videos = item.videos_in_folder
      }
      continue
    }
    grouped.set(key, {
      key,
      title: item.movie_folder ?? item.parent,
      subtitle: item.movie_folder_path ?? item.parent,
      items: [item],
      videos: item.videos_in_folder,
    })
  }
  return [...grouped.values()]
}
