import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import tsj from "ts-json-schema-generator";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const typesPath = path.resolve(__dirname, "../src/core/types.ts");
const tsconfigPath = path.resolve(__dirname, "../tsconfig.json");
const outDir = path.resolve(__dirname, "../../sdk-server-python/ghost_cursor/schemas");

fs.mkdirSync(outDir, { recursive: true });

const types = ["BrowserStartRequest", "BrowserContinueRequest", "PublicResponse"];

const generatorModule = tsj.default || tsj;

for (const type of types) {
  const config = {
    path: typesPath,
    tsconfig: tsconfigPath,
    type,
    additionalProperties: false,
    expose: "all",
    topRef: true,
  };
  const generator = generatorModule.createGenerator
    ? generatorModule.createGenerator(config)
    : new generatorModule.SchemaGenerator(config);
  const schema = generator.createSchema(type);
  const outPath = path.join(outDir, `${type}.json`);
  fs.writeFileSync(outPath, JSON.stringify(schema, null, 2) + "\n");
  console.log(`Generated schema: ${outPath}`);
}

