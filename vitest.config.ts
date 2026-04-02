import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  esbuild: {
    jsx: "automatic",
    jsxImportSource: "react",
  },
  resolve: {
    alias: {
      "@": path.resolve(rootDir, "apps/web"),
      "@quotes4/contracts": path.resolve(
        rootDir,
        "packages/contracts/src/index.ts",
      ),
      "@quotes4/domain": path.resolve(rootDir, "packages/domain/src/index.ts"),
    }
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"]
    }
  }
});
