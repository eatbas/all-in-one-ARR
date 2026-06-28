/**
 * Shared test helper that asserts a `SettingsHelp` icon button — located by its
 * accessible name — reveals the expected tooltip copy on hover. Centralised so
 * the settings suites do not each re-declare the same assertion.
 */
import { screen } from "@testing-library/react"
import type { UserEvent } from "@testing-library/user-event"
import { expect } from "vitest"

/** Hover the help button named `name` and assert `text` appears in a tooltip. */
export async function expectHelpTooltip(
  user: UserEvent,
  name: string,
  text: string,
): Promise<void> {
  await user.hover(screen.getByRole("button", { name }))
  expect((await screen.findAllByText(text)).length).toBeGreaterThan(0)
}
