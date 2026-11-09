import { existsSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { resolve } from "node:path";
import { type Plugin } from "vite";
import { defineConfig } from "vitest/config";
import { generateFixtures } from "./fixtures/generate";

const publicDir = resolve(__dirname, "public");

function serveFixture(req: IncomingMessage, res: ServerResponse, next: () => void): void {
  const url = (req.url ?? "").split("?")[0];
  if (!url.startsWith("/data/") || existsSync(resolve(publicDir, url.slice(1)))) {
    next();
    return;
  }
  const body = generateFixtures().get(url);
  if (body === undefined) {
    next();
    return;
  }
  res.setHeader("content-type", "application/json");
  res.end(JSON.stringify(body));
}

/** In dev and preview, serve demo data when the analysis has not written real data yet. */
function demoData(): Plugin {
  return {
    name: "demo-data",
    configureServer: (server) => void server.middlewares.use(serveFixture),
    configurePreviewServer: (server) => void server.middlewares.use(serveFixture),
  };
}

export default defineConfig({
  plugins: [demoData()],
  build: { target: "es2022" },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
