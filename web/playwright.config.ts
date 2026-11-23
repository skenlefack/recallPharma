import { defineConfig } from "@playwright/test";

/**
 * Parcours de bout en bout sur l'API locale chargée avec le jeu A10.
 * Prérequis : API démarrée sur :8000 avec RECALLPHARMA_REFERENCE_DATE=2027-09-07, puis `pnpm build`.
 */
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: { baseURL: "http://localhost:3100", locale: "fr-FR", timezoneId: "Africa/Douala" },
  webServer: {
    command: "pnpm start --port 3100",
    url: "http://localhost:3100",
    reuseExistingServer: true,
    env: { RECALLPHARMA_API_URL: process.env.RECALLPHARMA_API_URL ?? "http://127.0.0.1:8000" },
  },
});
