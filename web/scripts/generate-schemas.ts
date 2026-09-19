/**
 * Generate a Zodios client from the backend's OpenAPI schema.
 */

import { generateZodClientFromOpenAPI } from "openapi-zod-client";
import { mkdirSync } from "fs";
import { resolve } from "path";

type OpenAPIObject = Parameters<
  typeof generateZodClientFromOpenAPI
>[0]["openApiDoc"];

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const SCHEMA_URL = `${BACKEND_URL}/api/schema/no-error/`;
const OUTPUT_DIR = resolve(import.meta.dirname, "../src/schemas/backend");
const OUTPUT_FILE = resolve(OUTPUT_DIR, "index.ts");

async function generateSchemas() {
  console.log("🔧 Generating Zodios schemas from OpenAPI...");
  console.log(`   Fetching schema from: ${SCHEMA_URL}`);

  try {
    const response = await fetch(SCHEMA_URL, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(
        `${SCHEMA_URL} returned ${response.status}. Is the backend running?`
      );
    }
    const openApiDoc = (await response.json()) as OpenAPIObject;

    mkdirSync(OUTPUT_DIR, { recursive: true });

    // distPath is the file to write, not a directory.
    await generateZodClientFromOpenAPI({
      openApiDoc,
      distPath: OUTPUT_FILE,
    });

    console.log(`✅ Zodios schemas generated at ${OUTPUT_FILE}`);
  } catch (error) {
    console.error("❌ Failed to generate schemas:", error);
    process.exit(1);
  }
}

generateSchemas();
