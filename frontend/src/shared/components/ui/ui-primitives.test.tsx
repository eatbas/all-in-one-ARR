/**
 * Direct coverage for the vendored shadcn primitives whose `asChild` branches
 * and exported sub-components are not exercised by the page/component tests.
 */
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type * as Recharts from "recharts"
import type { TooltipPayload } from "recharts"
import { Line, LineChart } from "recharts"
import { describe, expect, it, vi } from "vitest"

import { Badge } from "@/shared/components/ui/badge"
import { Button } from "@/shared/components/ui/button"
import { Slider } from "@/shared/components/ui/slider"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card"
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuPortal,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog"
import {
  ChartContainer,
  ChartTooltipContent,
  type ChartConfig,
} from "@/shared/components/ui/chart"

// `vi.mock` is hoisted above the imports, so the helper is loaded inside it.
vi.mock("recharts", async (importOriginal) => {
  const { withFixedResponsiveContainer } =
    await import("@/shared/test/recharts")
  return withFixedResponsiveContainer(await importOriginal<typeof Recharts>())
})

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
          <DropdownMenuRadioGroup value="one">
            <DropdownMenuRadioItem value="one">First</DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
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
    expect(screen.getByText("First")).toBeInTheDocument()
    expect(screen.getByText("More")).toBeInTheDocument()
  })
})

describe("Select grouped options", () => {
  it("renders an open select with a grouped item", async () => {
    render(
      <Select defaultOpen>
        <SelectTrigger>
          <SelectValue placeholder="Pick" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value="alpha">Alpha</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>,
    )
    expect(await screen.findByText("Alpha")).toBeInTheDocument()
  })
})

describe("AlertDialog open content", () => {
  it("renders the trigger and portalled header, body and actions when open", async () => {
    render(
      <AlertDialog defaultOpen>
        <AlertDialogTrigger>Open</AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete?</AlertDialogTitle>
            <AlertDialogDescription>This is permanent.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction>Confirm</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>,
    )
    expect(await screen.findByText("Delete?")).toBeInTheDocument()
    expect(screen.getByText("This is permanent.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument()
  })
})

describe("Tooltip open content", () => {
  it("renders the trigger and portalled content when open by default", async () => {
    render(
      <TooltipProvider>
        <Tooltip defaultOpen>
          <TooltipTrigger>Hover me</TooltipTrigger>
          <TooltipContent sideOffset={4}>Tip text</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    )
    expect(screen.getByText("Hover me")).toBeInTheDocument()
    // Radix renders the open content into a portal (and a visually-hidden copy for
    // assistive tech), so assert at least one match rather than a unique node.
    expect((await screen.findAllByText("Tip text")).length).toBeGreaterThan(0)
  })
})

describe("Slider", () => {
  it("exposes a labelled thumb and steps with the keyboard", async () => {
    const user = userEvent.setup()
    render(
      <Slider
        aria-label="Density"
        min={5}
        max={11}
        step={1}
        defaultValue={[5]}
      />,
    )
    // Radix places the `slider` role and its accessible name on the thumb; the
    // wrapper must forward `aria-label` there for this query to resolve.
    const thumb = screen.getByRole("slider", { name: "Density" })
    expect(thumb).toHaveAttribute("aria-valuenow", "5")
    thumb.focus()
    await user.keyboard("{ArrowRight}")
    expect(thumb).toHaveAttribute("aria-valuenow", "6")
  })

  it("does not duplicate shared accessible names across range thumbs", () => {
    render(
      <Slider
        aria-label="Price range"
        aria-labelledby="price-range-label"
        value={[25, 75]}
      />,
    )

    const thumbs = screen.getAllByRole("slider")
    expect(thumbs).toHaveLength(2)
    for (const thumb of thumbs) {
      expect(thumb).not.toHaveAttribute("aria-label", "Price range")
      expect(thumb).not.toHaveAttribute("aria-labelledby", "price-range-label")
    }
  })

  it("defaults to one thumb at the minimum when no values are supplied", () => {
    render(<Slider aria-label="Density" min={5} max={11} />)

    expect(screen.getByRole("slider", { name: "Density" })).toHaveAttribute(
      "aria-valuenow",
      "5",
    )
  })
})

describe("Chart", () => {
  const config = {
    missing: { label: "Missing", color: "var(--chart-1)" },
    files: {
      label: "With files",
      theme: { light: "#111111", dark: "#eeeeee" },
    },
    plain: { label: "No colour" },
    lightOnly: { label: "Light only", theme: { light: "#222222", dark: "" } },
  } satisfies ChartConfig

  it("injects colour variables for the light and dark selectors", () => {
    const { container } = render(
      <ChartContainer id="library" config={config}>
        <LineChart data={[{ day: "1 Oct", missing: 3 }]}>
          <Line dataKey="missing" />
        </LineChart>
      </ChartContainer>,
    )

    const chart = container.querySelector('[data-slot="chart"]')
    expect(chart).toHaveAttribute("data-chart", "chart-library")
    const css = container.querySelector("style")?.innerHTML ?? ""
    expect(css).toContain(" [data-chart=chart-library] {")
    expect(css).toContain(".dark [data-chart=chart-library] {")
    expect(css).toContain("--color-missing: var(--chart-1);")
    expect(css).toContain("--color-files: #111111;")
    expect(css).toContain("--color-files: #eeeeee;")
    expect(css).not.toContain("--color-plain")
    expect(css.match(/--color-lightOnly: #222222;/g)).toHaveLength(1)
    expect(container.querySelector(".recharts-surface")).toBeInTheDocument()
  })

  it("omits the style element when no series has a colour", () => {
    const { container } = render(
      <ChartContainer config={{ plain: { label: "Plain" } }}>
        <LineChart data={[]} />
      </ChartContainer>,
    )

    expect(container.querySelector("style")).toBeNull()
    expect(
      container
        .querySelector('[data-slot="chart"]')
        ?.getAttribute("data-chart"),
    ).toMatch(/^chart-/)
  })

  const payload: TooltipPayload = [
    {
      dataKey: "missing",
      name: "missing",
      value: 1234,
      color: "red",
      graphicalItemId: "line-missing",
    },
    {
      name: "unconfigured",
      value: 7,
      color: "blue",
      graphicalItemId: "line-2",
    },
    { value: "n/a", color: "green", graphicalItemId: "line-3" },
    {
      dataKey: "hidden",
      name: "hidden",
      value: 1,
      type: "none",
      graphicalItemId: "line-hidden",
    },
  ]

  function renderTooltip(
    props: React.ComponentProps<typeof ChartTooltipContent>,
  ) {
    return render(
      <ChartContainer config={config}>
        <ChartTooltipContent {...props} />
      </ChartContainer>,
    )
  }

  it("renders nothing while the tooltip is inactive or empty", () => {
    const { container, unmount } = renderTooltip({
      active: false,
      payload,
      label: "1 Oct",
      className: "test-tooltip",
    })
    expect(container.querySelector(".test-tooltip")).toBeNull()
    unmount()

    const empty = renderTooltip({
      active: true,
      payload: [],
      label: "1 Oct",
      className: "test-tooltip",
    })
    expect(empty.container.querySelector(".test-tooltip")).toBeNull()
  })

  it("renders the label and each series with default number formatting", () => {
    renderTooltip({ active: true, payload, label: "1 Oct" })

    expect(screen.getByText("1 Oct")).toBeInTheDocument()
    expect(screen.getByText("Missing")).toBeInTheDocument()
    expect(screen.getByText((1234).toLocaleString())).toBeInTheDocument()
    expect(screen.getByText("unconfigured")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.queryByText("n/a")).not.toBeInTheDocument()
    expect(screen.queryByText("hidden")).not.toBeInTheDocument()
  })

  it("applies the label and value formatters", () => {
    renderTooltip({
      active: true,
      payload,
      label: "2026-10-01",
      labelFormatter: (label) => `Day ${String(label)}`,
      valueFormatter: (value, key) => `${key}=${value}`,
    })

    expect(screen.getByText("Day 2026-10-01")).toBeInTheDocument()
    expect(screen.getByText("missing=1234")).toBeInTheDocument()
    expect(screen.getByText("unconfigured=7")).toBeInTheDocument()
  })

  it("hides the label on request", () => {
    renderTooltip({ active: true, payload, label: "1 Oct", hideLabel: true })
    expect(screen.queryByText("1 Oct")).not.toBeInTheDocument()
  })

  it("throws when tooltip content is used outside a chart container", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    expect(() =>
      render(<ChartTooltipContent active payload={payload} />),
    ).toThrow("useChart must be used within a <ChartContainer />")
    consoleError.mockRestore()
  })
})
