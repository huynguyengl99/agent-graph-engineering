/**
 * Generate TypeScript types from AsyncAPI schema (WebSocket messages)
 *
 * Fetches AsyncAPI spec from backend and generates TypeScript types
 * for WebSocket message payloads.
 */

import { writeFileSync, mkdirSync } from "fs";
import { resolve } from "path";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const ASYNCAPI_URL = `${BACKEND_URL}/api/asyncapi/schema/`;
const OUTPUT_DIR = resolve(import.meta.dirname, "../src/types/websocket");

interface AsyncAPISchema {
  channels?: Record<string, any>;
  components?: {
    messages?: Record<string, any>;
    schemas?: Record<string, any>;
  };
}

async function generateWSTypes() {
  console.log("🔧 Generating WebSocket types from AsyncAPI...");
  console.log(`   Fetching schema from: ${ASYNCAPI_URL}`);

  try {
    // Fetch AsyncAPI schema
    const response = await fetch(ASYNCAPI_URL, {
      headers: { Accept: "application/json" },
    });
    const schema: AsyncAPISchema = await response.json();

    // Ensure output directory exists
    mkdirSync(OUTPUT_DIR, { recursive: true });

    // Generate schema types
    const schemaTypes = generateSchemaTypes(schema.components?.schemas || {});
    writeFileSync(
      resolve(OUTPUT_DIR, "schema.ts"),
      `/**
 * Generated WebSocket schema types
 *
 * DO NOT EDIT - Auto-generated from AsyncAPI
 * Run \`pnpm gen:ws\` to regenerate
 */

${schemaTypes}
`
    );

    // Generate message types for each channel
    for (const [channelName, channel] of Object.entries(schema.channels || {})) {
      const types = generateChannelTypes(channelName, channel, schema);
      const fileName = `${channelName}.ts`;

      writeFileSync(
        resolve(OUTPUT_DIR, fileName),
        `/**
 * Generated WebSocket types for ${channelName} channel
 *
 * DO NOT EDIT - Auto-generated from AsyncAPI
 * Run \`pnpm gen:ws\` to regenerate
 */

${types}
`
      );
      console.log(`   ✓ Generated ${fileName}`);
    }

    console.log(`✅ WebSocket types generated at ${OUTPUT_DIR}`);
  } catch (error) {
    console.error("❌ Failed to generate WebSocket types:", error);
    process.exit(1);
  }
}

function generateSchemaTypes(schemas: Record<string, any>): string {
  return Object.entries(schemas)
    .map(([name, schema]) => {
      if (schema.type === "object") {
        const properties = schema.properties || {};
        const required = new Set(schema.required || []);

        const fields = Object.entries(properties)
          .map(([fieldName, fieldSchema]: [string, any]) => {
            const optional = !required.has(fieldName) ? "?" : "";
            const type = schemaToTSType(fieldSchema);
            return `  ${fieldName}${optional}: ${type};`;
          })
          .join("\n");

        return `export interface ${name} {\n${fields}\n}`;
      }
      return `export type ${name} = any;`;
    })
    .join("\n\n");
}

function generateChannelTypes(
  _channelName: string,
  channel: any,
  schema: AsyncAPISchema
): string {
  const messages = schema.components?.messages || {};
  let output = "";

  // Extract message types for this channel
  if (channel.subscribe?.message?.oneOf) {
    output += "// Incoming messages (from server)\n";
    for (const msgRef of channel.subscribe.message.oneOf) {
      const msgName = msgRef.$ref?.split("/").pop();
      if (msgName && messages[msgName]) {
        output += `export type ${msgName} = Schema.${msgName};\n`;
      }
    }
    output += "\n";
  }

  if (channel.publish?.message?.oneOf) {
    output += "// Outgoing messages (to server)\n";
    for (const msgRef of channel.publish.message.oneOf) {
      const msgName = msgRef.$ref?.split("/").pop();
      if (msgName && messages[msgName]) {
        output += `export type ${msgName} = Schema.${msgName};\n`;
      }
    }
  }

  return output;
}

function schemaToTSType(schema: any): string {
  if (schema.$ref) {
    return schema.$ref.split("/").pop();
  }

  if (schema.type === "string") return "string";
  if (schema.type === "number" || schema.type === "integer") return "number";
  if (schema.type === "boolean") return "boolean";
  if (schema.type === "array") {
    return `${schemaToTSType(schema.items || {})}[]`;
  }
  if (schema.type === "object") return "Record<string, any>";

  return "any";
}

generateWSTypes();
