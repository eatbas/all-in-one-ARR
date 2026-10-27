/**
 * Vendored shadcn/ui `chart` primitive (new-york-v4 registry, Recharts 3),
 * trimmed to the pieces the dashboard uses: the container with its
 * theme-aware colour variables and the tooltip content. The legend, icon and
 * line/dashed indicator variants were dropped; tooltip values are formatted
 * through `valueFormatter` instead of Recharts' whole-row `formatter`.
 */
import * as React from "react"
import * as RechartsPrimitive from "recharts"
import type { TooltipPayload } from "recharts"

import { cn } from "@/shared/lib/utils"

// Format: { THEME_NAME: CSS_SELECTOR }
const THEMES = { light: "", dark: ".dark" } as const

const INITIAL_DIMENSION = { width: 320, height: 200 } as const

/** Per-series label and colour, exposed to the chart as `--color-<key>`. */
export type ChartConfig = Record<
  string,
  {
    label?: React.ReactNode
  } & (
    | { color?: string; theme?: never }
    | { color?: never; theme: Record<keyof typeof THEMES, string> }
  )
>

type ChartContextProps = {
  config: ChartConfig
}

const ChartContext = React.createContext<ChartContextProps | null>(null)

function useChart() {
  const context = React.useContext(ChartContext)

  if (!context) {
    throw new Error("useChart must be used within a <ChartContainer />")
  }

  return context
}

function ChartContainer({
  id,
  className,
  children,
  config,
  initialDimension = INITIAL_DIMENSION,
  ...props
}: React.ComponentProps<"div"> & {
  config: ChartConfig
  children: React.ComponentProps<
    typeof RechartsPrimitive.ResponsiveContainer
  >["children"]
  initialDimension?: {
    width: number
    height: number
  }
}) {
  const uniqueId = React.useId()
  const chartId = `chart-${id ?? uniqueId.replace(/:/g, "")}`

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-slot="chart"
        data-chart={chartId}
        className={cn(
          "flex aspect-video justify-center text-xs [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-cartesian-grid_line[stroke='#ccc']]:stroke-border/50 [&_.recharts-curve.recharts-tooltip-cursor]:stroke-border [&_.recharts-dot[stroke='#fff']]:stroke-transparent [&_.recharts-layer]:outline-hidden [&_.recharts-rectangle.recharts-tooltip-cursor]:fill-muted [&_.recharts-reference-line_[stroke='#ccc']]:stroke-border [&_.recharts-surface]:outline-hidden",
          className,
        )}
        {...props}
      >
        <ChartStyle id={chartId} config={config} />
        <RechartsPrimitive.ResponsiveContainer
          initialDimension={initialDimension}
        >
          {children}
        </RechartsPrimitive.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  )
}

const ChartStyle = ({ id, config }: { id: string; config: ChartConfig }) => {
  const colorConfig = Object.entries(config).filter(
    ([, config]) => config.theme ?? config.color,
  )

  if (!colorConfig.length) {
    return null
  }

  return (
    <style
      dangerouslySetInnerHTML={{
        __html: Object.entries(THEMES)
          .map(
            ([theme, prefix]) => `
${prefix} [data-chart=${id}] {
${colorConfig
  .map(([key, itemConfig]) => {
    const color =
      itemConfig.theme?.[theme as keyof typeof itemConfig.theme] ??
      itemConfig.color
    return color ? `  --color-${key}: ${color};` : null
  })
  .join("\n")}
}
`,
          )
          .join("\n"),
      }}
    />
  )
}

const ChartTooltip = RechartsPrimitive.Tooltip

/** Props Recharts injects into tooltip content, plus display options. */
type ChartTooltipContentProps = {
  active?: boolean
  payload?: TooltipPayload
  label?: React.ReactNode
  className?: string
  hideLabel?: boolean
  labelFormatter?: (label: React.ReactNode) => React.ReactNode
  valueFormatter?: (value: number, dataKey: string) => React.ReactNode
}

function ChartTooltipContent({
  active,
  payload,
  label,
  className,
  hideLabel = false,
  labelFormatter,
  valueFormatter,
}: ChartTooltipContentProps) {
  const { config } = useChart()

  if (!active || !payload?.length) {
    return null
  }

  return (
    <div
      className={cn(
        "grid min-w-[8rem] items-start gap-1.5 rounded-lg border border-border/50 bg-background px-2.5 py-1.5 text-xs shadow-xl",
        className,
      )}
    >
      {hideLabel ? null : (
        <div className="font-medium">
          {labelFormatter ? labelFormatter(label) : label}
        </div>
      )}
      <div className="grid gap-1.5">
        {payload
          .filter((item) => item.type !== "none")
          .map((item) => {
            const key = `${item.dataKey ?? item.name ?? "value"}`
            const itemConfig = config[key]

            return (
              <div key={key} className="flex w-full items-center gap-2">
                <div
                  className="h-2.5 w-2.5 shrink-0 rounded-[2px] bg-(--color-bg)"
                  style={{ "--color-bg": item.color } as React.CSSProperties}
                />
                <div className="flex flex-1 items-center justify-between gap-2 leading-none">
                  <span className="text-muted-foreground">
                    {itemConfig?.label ?? item.name}
                  </span>
                  {typeof item.value === "number" && (
                    <span className="font-mono font-medium text-foreground tabular-nums">
                      {valueFormatter
                        ? valueFormatter(item.value, key)
                        : item.value.toLocaleString()}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
      </div>
    </div>
  )
}

export { ChartContainer, ChartTooltip, ChartTooltipContent, ChartStyle }
