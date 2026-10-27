/**
 * Recharts test helper. jsdom has no layout, so a `ResponsiveContainer` never
 * measures a size (the global `ResizeObserver` stub never fires) and charts
 * would render an empty surface. Pass this to `vi.mock("recharts", ...)` to
 * swap in a container with a fixed 800×300 size so axes, lines, areas and bars
 * render into the DOM. `vi.mock` is hoisted above static imports, so load the
 * helper inside the factory:
 *
 *   vi.mock("recharts", async (importOriginal) => {
 *     const { withFixedResponsiveContainer } = await import("@/shared/test/recharts")
 *     return withFixedResponsiveContainer(await importOriginal<typeof Recharts>())
 *   })
 */
import { forwardRef, type ComponentProps } from "react"
import type * as Recharts from "recharts"

/** Fixed chart size used in tests. */
export const TEST_CHART_SIZE = { width: 800, height: 300 } as const

type ResponsiveContainerProps = ComponentProps<
  typeof Recharts.ResponsiveContainer
>

/** Return the Recharts module with a fixed-size `ResponsiveContainer`. */
export function withFixedResponsiveContainer(
  actual: typeof Recharts,
): typeof Recharts {
  const ActualContainer = actual.ResponsiveContainer

  const FixedResponsiveContainer = forwardRef<
    HTMLDivElement,
    ResponsiveContainerProps
  >(function FixedResponsiveContainer({ children }, ref) {
    return (
      <ActualContainer
        ref={ref}
        width={TEST_CHART_SIZE.width}
        height={TEST_CHART_SIZE.height}
      >
        {children}
      </ActualContainer>
    )
  })

  return { ...actual, ResponsiveContainer: FixedResponsiveContainer }
}
