import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it, expect } from "vitest";
import { validateBrowserRequest, GatewayError } from "../src/index.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../../fixtures/protocol");

const validFiles = fs
  .readdirSync(path.join(FIXTURES_DIR, "valid"))
  .filter((f) => f.endsWith(".json"))
  .sort();

const invalidFiles = fs
  .readdirSync(path.join(FIXTURES_DIR, "invalid"))
  .filter((f) => f.endsWith(".json"))
  .sort();

describe("Protocol Parity Tests (Node Gateway)", () => {
  it("has at least 10 valid and 10 invalid fixtures", () => {
    expect(validFiles.length).toBeGreaterThanOrEqual(10);
    expect(invalidFiles.length).toBeGreaterThanOrEqual(10);
  });

  describe("Valid protocol fixtures", () => {
    for (const file of validFiles) {
      it(`validates ${file} successfully`, () => {
        const filePath = path.join(FIXTURES_DIR, "valid", file);
        const data = JSON.parse(fs.readFileSync(filePath, "utf-8"));
        const validated = validateBrowserRequest(data);
        expect(validated).toBeDefined();
        expect(validated.command).toBe(data.command);
      });
    }
  });

  describe("Invalid protocol fixtures", () => {
    for (const file of invalidFiles) {
      it(`rejects ${file} with 400 invalid_request`, () => {
        const filePath = path.join(FIXTURES_DIR, "invalid", file);
        const data = JSON.parse(fs.readFileSync(filePath, "utf-8"));
        expect(() => validateBrowserRequest(data)).toThrowError(GatewayError);
        try {
          validateBrowserRequest(data);
        } catch (err: any) {
          expect(err.status).toBe(400);
          expect(err.code).toBe("invalid_request");
        }
      });
    }
  });
});

