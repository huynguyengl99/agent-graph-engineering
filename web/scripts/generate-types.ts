/**
 * Generate pure TypeScript types from the backend's OpenAPI schema.
 *
 * Everything lands in a single file. Splitting by tag was the previous design
 * and it emitted `$ref` names that lived in a sibling file with no import,
 * so the output never typechecked. Types have no runtime cost and TS hoists
 * declarations, so one file is both simpler and correct.
 */

import { mkdirSync, writeFileSync } from "fs";
import { resolve } from "path";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const SCHEMA_URL = `${BACKEND_URL}/api/schema/no-error/`;
const OUTPUT_DIR = resolve(import.meta.dirname, "../src/types/backend");
const OUTPUT_FILE = resolve(OUTPUT_DIR, "index.ts");

type JsonSchema = Record<string, any>;

interface OpenAPISchema {
  components?: { schemas?: Record<string, JsonSchema> };
}

async function generateTypes(): Promise<void> {
  console.log("🔧 Generating TypeScript types from OpenAPI...");
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
    const schema = (await response.json()) as OpenAPISchema;
    const components = schema.components?.schemas ?? {};

    const declarations = Object.entries(components)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, definition]) => declare(name, definition))
      .join("\n\n");

    mkdirSync(OUTPUT_DIR, { recursive: true });
    writeFileSync(
      OUTPUT_FILE,
      `/**
 * Generated from the backend OpenAPI schema.
 *
 * DO NOT EDIT. Run \`pnpm gen:type\` to regenerate.
 */

${declarations}
`
    );

    const count = Object.keys(components).length;
    console.log(`   ✓ ${count} schemas`);
    console.log(`✅ TypeScript types generated at ${OUTPUT_FILE}`);
  } catch (error) {
    console.error("❌ Failed to generate types:", error);
    process.exit(1);
  }
}

function declare(name: string, schema: JsonSchema): string {
  const doc = schema.description ? `/** ${oneLine(schema.description)} */\n` : "";

  if (Array.isArray(schema.oneOf)) {
    return `${doc}${discriminatedUnion(name, schema)}`;
  }
  if (Array.isArray(schema.enum)) {
    return `${doc}export type ${name} = ${schema.enum
      .map((value: unknown) => JSON.stringify(value))
      .join(" | ")};`;
  }
  if (schema.properties || schema.type === "object") {
    return `${doc}export interface ${name} ${objectBody(schema)}`;
  }
  return `${doc}export type ${name} = ${tsType(schema)};`;
}

/**
 * The polymorphic `TicketEvent` is the reason this repo exists, so it gets a
 * real union rather than `any`. The discriminator mapping is emitted as a
 * comment because the variants already carry the literal themselves.
 */
function discriminatedUnion(name: string, schema: JsonSchema): string {
  const variants = (schema.oneOf as JsonSchema[])
    .map((variant) => tsType(variant))
    .filter(Boolean);

  const propertyName = schema.discriminator?.propertyName;
  const note = propertyName
    ? `/** Discriminated on \`${propertyName}\`. */\n`
    : "";

  return `${note}export type ${name} =\n  | ${variants.join("\n  | ")};`;
}

function objectBody(schema: JsonSchema): string {
  const properties: Record<string, JsonSchema> = schema.properties ?? {};
  const required = new Set<string>(schema.required ?? []);

  const fields = Object.entries(properties)
    .map(([field, definition]) => {
      const optional = required.has(field) ? "" : "?";
      const doc = definition.description
        ? `  /** ${oneLine(definition.description)} */\n`
        : "";
      return `${doc}  ${quoteKey(field)}${optional}: ${tsType(definition)};`;
    })
    .join("\n");

  return fields ? `{\n${fields}\n}` : "{\n  [key: string]: unknown;\n}";
}

function tsType(schema: JsonSchema | undefined): string {
  if (!schema) return "unknown";

  if (schema.$ref) {
    return String(schema.$ref).split("/").pop() ?? "unknown";
  }

  if (Array.isArray(schema.enum)) {
    return schema.enum.map((value: unknown) => JSON.stringify(value)).join(" | ");
  }

  if (Array.isArray(schema.oneOf)) {
    return schema.oneOf.map(tsType).join(" | ");
  }
  if (Array.isArray(schema.allOf)) {
    return schema.allOf.map(tsType).join(" & ");
  }
  if (Array.isArray(schema.anyOf)) {
    return schema.anyOf.map(tsType).join(" | ");
  }

  const base = primitive(schema);
  return schema.nullable ? `${base} | null` : base;
}

function primitive(schema: JsonSchema): string {
  switch (schema.type) {
    case "string":
      return "string";
    case "number":
    case "integer":
      return "number";
    case "boolean":
      return "boolean";
    case "array":
      return `${tsType(schema.items)}[]`;
    case "object":
      return schema.properties
        ? objectBody(schema)
        : `Record<string, ${tsType(schema.additionalProperties)}>`;
    default:
      return "unknown";
  }
}

const SAFE_KEY = /^[A-Za-z_$][A-Za-z0-9_$]*$/;

function quoteKey(key: string): string {
  return SAFE_KEY.test(key) ? key : JSON.stringify(key);
}

function oneLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

generateTypes();
