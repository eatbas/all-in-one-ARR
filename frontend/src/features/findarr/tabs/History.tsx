import { Badge } from "@/shared/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table"
import { formatTimestamp } from "@/shared/lib/format"
import { useFindarrHistory } from "@/shared/lib/queries"

export function History() {
  const { data: history, isLoading } = useFindarrHistory()

  if (isLoading || !history) {
    return <p className="text-sm text-muted-foreground">Loading history…</p>
  }
  if (history.length === 0) {
    return <p className="text-sm text-muted-foreground">No Findarr history yet.</p>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>App</TableHead>
          <TableHead>Mode</TableHead>
          <TableHead>Title</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Detail</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {history.map((entry) => (
          <TableRow key={entry.id}>
            <TableCell>{formatTimestamp(entry.ts)}</TableCell>
            <TableCell className="capitalize">{entry.app}</TableCell>
            <TableCell className="capitalize">{entry.mode}</TableCell>
            <TableCell>{entry.title ?? entry.item_id ?? "System"}</TableCell>
            <TableCell>
              <Badge variant={entry.status === "error" ? "destructive" : "outline"}>
                {entry.status}
              </Badge>
            </TableCell>
            <TableCell>{entry.detail}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
