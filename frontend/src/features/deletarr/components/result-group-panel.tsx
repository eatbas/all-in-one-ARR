import { useState } from "react"
import { ChevronDownIcon, FolderIcon } from "lucide-react"

import { Badge } from "@/shared/components/ui/badge"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible"
import { formatBytes } from "@/shared/lib/format"
import type { DeletarrScanItem } from "@/shared/lib/api"

export interface ResultGroup {
  key: string
  title: string
  subtitle: string
  items: DeletarrScanItem[]
  videos: DeletarrScanItem["videos_in_folder"]
}

function sumSize(items: DeletarrScanItem[]): number {
  return items.reduce((total, item) => total + item.size, 0)
}

interface ResultGroupPanelProps {
  group: ResultGroup
  selectedSet: Set<string>
  onGroupSelection: (group: ResultGroup, checked: boolean) => void
  onItemSelection: (path: string, checked: boolean) => void
}

/** Render one grouped folder of Deletarr scan candidates. */
export function ResultGroupPanel({
  group,
  selectedSet,
  onGroupSelection,
  onItemSelection,
}: ResultGroupPanelProps) {
  const [isOpen, setIsOpen] = useState(true)
  const selectedCount = group.items.filter((item) =>
    selectedSet.has(item.path),
  ).length
  const allSelected = selectedCount === group.items.length
  const partiallySelected = selectedCount > 0 && !allSelected
  const groupSize = sumSize(group.items)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} asChild>
      <section
        className="rounded-lg border bg-background"
        aria-label={group.title}
      >
        <div className="flex flex-col gap-3 border-b p-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <FolderIcon className="size-4 shrink-0 text-muted-foreground" />
              <h3 className="truncate text-sm font-semibold">{group.title}</h3>
              <Badge variant="secondary">{formatBytes(groupSize)}</Badge>
            </div>
            <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
              {group.subtitle}
            </p>
            {group.videos.length > 0 ? (
              <p className="mt-2 text-xs text-muted-foreground">
                Protected video:{" "}
                {group.videos.map((video) => video.name).join(", ")}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={allSelected}
                ref={(element) => {
                  if (element) element.indeterminate = partiallySelected
                }}
                onChange={(event) =>
                  onGroupSelection(group, event.target.checked)
                }
              />
              Select group
            </label>
            <CollapsibleTrigger
              type="button"
              className="inline-flex size-8 items-center justify-center rounded-md border hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={`${isOpen ? "Collapse" : "Expand"} ${group.title}`}
            >
              <ChevronDownIcon
                aria-hidden="true"
                className={`size-4 transition-transform ${isOpen ? "" : "-rotate-90"}`}
              />
            </CollapsibleTrigger>
          </div>
        </div>

        <CollapsibleContent>
          <div className="divide-y">
            {group.items.map((item) => (
              <label
                key={item.path}
                className="grid gap-3 p-4 text-sm md:grid-cols-[auto_1fr_auto] md:items-center"
              >
                <input
                  type="checkbox"
                  checked={selectedSet.has(item.path)}
                  onChange={(event) =>
                    onItemSelection(item.path, event.target.checked)
                  }
                  aria-label={`Select ${item.name}`}
                />
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium">{item.name}</span>
                    <Badge
                      variant={item.type === "folder" ? "outline" : "secondary"}
                    >
                      {item.type}
                    </Badge>
                  </span>
                  <span className="mt-1 block break-all font-mono text-xs text-muted-foreground">
                    {item.path}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {item.reason}
                  </span>
                </span>
                <span className="text-sm font-medium md:text-right">
                  {formatBytes(item.size)}
                </span>
              </label>
            ))}
          </div>
        </CollapsibleContent>
      </section>
    </Collapsible>
  )
}
