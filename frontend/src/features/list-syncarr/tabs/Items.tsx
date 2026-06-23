import { useState } from "react"
import { ChevronDownIcon, FilterIcon } from "lucide-react"

import { Button } from "@/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table"
import { StatusBadge } from "@/features/list-syncarr/components/status-badge"
import { useItems } from "@/shared/lib/queries"
import { displayTitle, formatTimestamp } from "@/shared/lib/format"
import type { ItemStatus } from "@/shared/lib/api"

/** "all" is the UI-only sentinel meaning "no status filter". */
type StatusFilter = ItemStatus | "all"

const STATUS_FILTERS: ReadonlyArray<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All statuses" },
  { value: "synced", label: "Synced" },
  { value: "requested", label: "Requested" },
  { value: "available", label: "Available" },
  { value: "removed", label: "Removed" },
]

/** Items page: filterable table of every mirrored movie and show. */
export function Items() {
  const [filter, setFilter] = useState<StatusFilter>("all")
  const { data: items, isLoading } = useItems(
    filter === "all" ? undefined : filter,
  )

  const activeOption = STATUS_FILTERS.find((option) => option.value === filter)
  // `filter` is always one of STATUS_FILTERS' values, so `activeOption` is never
  // undefined; the optional chain and fallback guard a type-unreachable state.
  /* v8 ignore next */
  const activeLabel = activeOption?.label ?? "All statuses"

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle>Items</CardTitle>
          <CardDescription>
            Every movie and show mirrored from Trakt.
          </CardDescription>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              <FilterIcon className="size-4" />
              {activeLabel}
              <ChevronDownIcon className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Filter by status</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuRadioGroup
              value={filter}
              onValueChange={(value) => setFilter(value as StatusFilter)}
            >
              {STATUS_FILTERS.map((option) => (
                <DropdownMenuRadioItem key={option.value} value={option.value}>
                  {option.label}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead className="w-20">Year</TableHead>
              <TableHead className="w-24">Type</TableHead>
              <TableHead className="w-28">List</TableHead>
              <TableHead className="w-28">Status</TableHead>
              <TableHead className="w-48">Last updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="py-8 text-center text-muted-foreground"
                >
                  Loading items…
                </TableCell>
              </TableRow>
            ) : (items?.length ?? 0) === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="py-8 text-center text-muted-foreground"
                >
                  No items match this filter.
                </TableCell>
              </TableRow>
            ) : (
              items?.map((item) => (
                <TableRow key={`${item.list_id}:${item.trakt_id}`}>
                  <TableCell className="font-medium">
                    {displayTitle(item.title)}
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">
                    {item.year ?? "—"}
                  </TableCell>
                  <TableCell className="capitalize text-muted-foreground">
                    {item.type}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {item.list_id}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={item.status} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatTimestamp(item.updated_at)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
