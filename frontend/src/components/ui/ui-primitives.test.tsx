/**
 * Direct coverage for the vendored shadcn primitives whose `asChild` branches
 * and exported sub-components are not exercised by the page/component tests.
 */
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuPortal,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

describe("Button asChild", () => {
  it("renders a slotted child instead of a button", () => {
    render(
      <Button asChild>
        <a href="/somewhere">Go</a>
      </Button>,
    )
    const link = screen.getByRole("link", { name: "Go" })
    expect(link).toHaveAttribute("data-slot", "button")
  })
})

describe("Badge asChild", () => {
  it("renders a slotted child instead of a span", () => {
    render(
      <Badge asChild>
        <a href="/elsewhere">Tag</a>
      </Badge>,
    )
    const link = screen.getByRole("link", { name: "Tag" })
    expect(link).toHaveAttribute("data-slot", "badge")
  })
})

describe("Card sub-components", () => {
  it("renders the header action and footer", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardDescription>Description</CardDescription>
          <CardAction>Action</CardAction>
        </CardHeader>
        <CardContent>Content</CardContent>
        <CardFooter>Footer</CardFooter>
      </Card>,
    )
    expect(screen.getByText("Action")).toBeInTheDocument()
    expect(screen.getByText("Footer")).toBeInTheDocument()
  })
})

describe("Table caption and footer", () => {
  it("renders a full table including caption and footer", () => {
    render(
      <Table>
        <TableCaption>Caption</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Head</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>Body</TableCell>
          </TableRow>
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell>Foot</TableCell>
          </TableRow>
        </TableFooter>
      </Table>,
    )
    expect(screen.getByText("Caption")).toBeInTheDocument()
    expect(screen.getByText("Foot")).toBeInTheDocument()
  })
})

describe("DropdownMenu extended parts", () => {
  it("renders groups, checkbox items, shortcuts, and a submenu", async () => {
    render(
      <DropdownMenu defaultOpen>
        <DropdownMenuTrigger>Open</DropdownMenuTrigger>
        <DropdownMenuPortal>
          <span>portal-child</span>
        </DropdownMenuPortal>
        <DropdownMenuContent sideOffset={8}>
          <DropdownMenuLabel inset>Section</DropdownMenuLabel>
          <DropdownMenuGroup>
            <DropdownMenuItem inset variant="destructive">
              Delete
              <DropdownMenuShortcut>⌘⌫</DropdownMenuShortcut>
            </DropdownMenuItem>
            <DropdownMenuCheckboxItem checked>Toggle</DropdownMenuCheckboxItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuSub defaultOpen>
            <DropdownMenuSubTrigger inset>More</DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              <DropdownMenuItem>Nested</DropdownMenuItem>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        </DropdownMenuContent>
      </DropdownMenu>,
    )

    expect(await screen.findByText("Section")).toBeInTheDocument()
    expect(screen.getByText("Toggle")).toBeInTheDocument()
    expect(screen.getByText("⌘⌫")).toBeInTheDocument()
    expect(screen.getByText("More")).toBeInTheDocument()
  })
})
