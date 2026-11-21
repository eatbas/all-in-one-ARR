import { Badge } from "@/shared/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table"
import type { RemindarrUnmatchedSeries } from "@/shared/lib/api"

interface UnmatchedSeriesProps {
  series: RemindarrUnmatchedSeries[]
}

/**
 * Tracked series that could not be matched to a Plex show by TVDB id. Their
 * watch state is unknown, so they are never counted as unwatched.
 */
export function UnmatchedSeries({ series }: UnmatchedSeriesProps) {
  if (series.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Not found in Plex ({series.length})</CardTitle>
        <CardDescription>
          These tagged series could not be matched to a Plex show by TVDB id, so
          their watch state is unknown and they are never counted as unwatched.
          Shows on Plex&apos;s legacy TheTVDB agent always land here.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Series</TableHead>
              <TableHead>Reason</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {series.map((item) => (
              <TableRow key={item.series_id}>
                <TableCell className="font-medium">
                  {item.series_title}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{item.reason_label}</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
