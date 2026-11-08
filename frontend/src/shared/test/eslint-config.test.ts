import { readFileSync } from "node:fs"
import { createRequire } from "node:module"
import path from "node:path"
import { ESLint } from "eslint"
import { describe, expect, it } from "vitest"

const frontendRoot = path.resolve(import.meta.dirname, "../../..")
const requireFromFrontend = createRequire(
  path.join(frontendRoot, "package.json"),
)

/** Exercise the repository configuration through ESLint's real Node API. */
describe("ESLint configuration", () => {
  it.each([
    "eslint",
    "@eslint/config-array",
    "@typescript-eslint/typescript-estree",
  ])("uses the patched matcher for %s", (consumer: string) => {
    const requireFromConsumer = createRequire(
      requireFromFrontend.resolve(consumer),
    )
    const matcher = JSON.parse(
      readFileSync(
        requireFromConsumer.resolve("minimatch/package.json"),
        "utf8",
      ),
    ) as { version: string }
    expect(matcher.version).toBe("11.0.5")
  })

  it.each([
    "src/features/example/nested/source.ts",
    "src/features/example/nested/Component.tsx",
    "src/features/example/nested/Component.test.tsx",
  ])("applies TypeScript rules to %s", async (filePath: string) => {
    const eslint = new ESLint({ cwd: frontendRoot })
    const config = await eslint.calculateConfigForFile(filePath)
    expect(config?.rules["@typescript-eslint/no-unused-vars"]).toBeDefined()
    expect(await eslint.isPathIgnored(filePath)).toBe(false)
  })

  it.each(["dist/nested/output.tsx", "coverage/nested/report.ts"])(
    "ignores generated output %s",
    async (filePath: string) => {
      const eslint = new ESLint({ cwd: frontendRoot })
      expect(await eslint.isPathIgnored(filePath)).toBe(true)
      expect(
        await eslint.lintText("const unused = 1", {
          filePath,
          warnIgnored: false,
        }),
      ).toEqual([])
    },
  )

  it.each([
    ["src/features/example/nested/source.ts", "const unused: number = 1"],
    [
      "src/features/example/nested/Component.tsx",
      "const unused = <div />; export default function Component() { return <div /> }",
    ],
  ])(
    "rejects unused values in %s",
    async (filePath: string, source: string) => {
      const eslint = new ESLint({ cwd: frontendRoot })
      const [result] = await eslint.lintText(source, { filePath })
      expect(result.fatalErrorCount).toBe(0)
      expect(result.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            ruleId: "@typescript-eslint/no-unused-vars",
            severity: 2,
          }),
        ]),
      )
    },
  )

  it.each([
    ["src/features/example/nested/source.ts", "export const value: number = 1"],
    [
      "src/features/example/nested/Component.tsx",
      "export default function Component() { return <div /> }",
    ],
  ])("accepts valid source in %s", async (filePath: string, source: string) => {
    const eslint = new ESLint({ cwd: frontendRoot })
    const [result] = await eslint.lintText(source, { filePath })
    expect(result.messages).toEqual([])
  })
})
