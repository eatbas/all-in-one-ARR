import * as React from "react"
import { type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/shared/lib/utils"
import { buttonVariants } from "@/shared/components/ui/button-variants"

// React 19: `ref` is a regular prop, so it flows through `...props` to the
// underlying element — Radix `asChild` triggers (e.g. DropdownMenuTrigger) still
// receive the element ref and anchor their popovers correctly, without
// `forwardRef` (deprecated in React 19).
function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button }
