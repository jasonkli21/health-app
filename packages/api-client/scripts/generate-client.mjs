import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { format } from "prettier";

const packageRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const specPath = path.resolve(
  packageRoot,
  "../../contracts/openapi/openapi.json",
);
const outputPath = path.resolve(packageRoot, "src/generated.ts");
const spec = JSON.parse(readFileSync(specPath, "utf8"));
const schemas = spec.components?.schemas ?? {};

function refName(ref) {
  const prefix = "#/components/schemas/";
  if (!ref.startsWith(prefix))
    throw new Error(`Unsupported OpenAPI reference: ${ref}`);
  return ref.slice(prefix.length);
}

function tsType(schema) {
  if (schema.$ref)
    return `components["schemas"][${JSON.stringify(refName(schema.$ref))}]`;
  if (Array.isArray(schema.type))
    return schema.type.map((type) => tsType({ ...schema, type })).join(" | ");
  if (schema.oneOf) return schema.oneOf.map(tsType).join(" | ");
  if (schema.anyOf) return schema.anyOf.map(tsType).join(" | ");
  if (schema.allOf) {
    const { allOf, ...base } = schema;
    const members = allOf.map(tsType).filter((member) => member !== "unknown");
    if (base.type || base.properties || base.additionalProperties)
      members.unshift(tsType(base));
    return members.length ? members.join(" & ") : "unknown";
  }
  if (schema.enum)
    return schema.enum.map((value) => JSON.stringify(value)).join(" | ");
  if (schema.const !== undefined) return JSON.stringify(schema.const);
  if (schema.type === "null") return "null";
  if (schema.type === "array") return `Array<${tsType(schema.items ?? {})}>`;
  if (
    schema.type === "object" ||
    schema.properties ||
    schema.additionalProperties
  ) {
    const properties = Object.entries(schema.properties ?? {});
    const required = new Set(schema.required ?? []);
    const members = properties.map(([name, property]) => {
      const safeName = /^[A-Za-z_$][\w$]*$/.test(name)
        ? name
        : JSON.stringify(name);
      return `    ${safeName}${required.has(name) ? "" : "?"}: ${tsType(property)};`;
    });
    if (schema.additionalProperties === true)
      members.push("    [key: string]: unknown;");
    else if (
      schema.additionalProperties &&
      typeof schema.additionalProperties === "object"
    ) {
      members.push(
        `    [key: string]: ${tsType(schema.additionalProperties)};`,
      );
    }
    return members.length
      ? ` {\n${members.join("\n")}\n  }`
      : "Record<string, never>";
  }
  if (schema.type === "string") return "string";
  if (schema.type === "integer" || schema.type === "number") return "number";
  if (schema.type === "boolean") return "boolean";
  return "unknown";
}

function operationList() {
  const result = [];
  for (const [route, methods] of Object.entries(spec.paths ?? {})) {
    for (const [method, operation] of Object.entries(methods)) {
      if (!operation.operationId)
        throw new Error(`Missing operationId for ${method} ${route}`);
      result.push({ route, method: method.toUpperCase(), operation });
    }
  }
  return result.sort((a, b) =>
    a.operation.operationId.localeCompare(b.operation.operationId),
  );
}

function parametersFor(operation, location) {
  return (operation.parameters ?? []).filter(
    (parameter) => parameter.in === location,
  );
}

function parameterObject(parameters) {
  const required = parameters
    .filter((parameter) => parameter.required)
    .map((parameter) => parameter.name);
  const properties = Object.fromEntries(
    parameters.map((parameter) => [parameter.name, parameter.schema]),
  );
  return { type: "object", properties, required };
}

function successSchema(operation) {
  const entry = Object.entries(operation.responses ?? {})
    .filter(([status]) => /^2\d\d$/.test(status))
    .sort(([left], [right]) => Number(left) - Number(right))
    .find(([, response]) => response.content?.["application/json"]?.schema);
  return entry?.[1].content["application/json"].schema ?? null;
}

const operations = operationList();
const lines = [
  "/* Generated from contracts/openapi/openapi.json. Do not edit by hand. */",
  "",
  "export interface components {",
  "  schemas: {",
];

for (const [name, schema] of Object.entries(schemas).sort(([a], [b]) =>
  a.localeCompare(b),
)) {
  lines.push(`    ${JSON.stringify(name)}: ${tsType(schema)};`);
}
lines.push("  }", "}", "", "export interface operations {");

for (const { operation } of operations) {
  const id = operation.operationId;
  const pathParameters = parametersFor(operation, "path");
  const queryParameters = parametersFor(operation, "query");
  const requestBody =
    operation.requestBody?.content?.["application/json"]?.schema;
  const response = successSchema(operation);
  const typeMembers = [];
  if (pathParameters.length)
    typeMembers.push(`path: ${tsType(parameterObject(pathParameters))};`);
  if (queryParameters.length) {
    const queryRequired = queryParameters.some(
      (parameter) => parameter.required,
    );
    typeMembers.push(
      `query${queryRequired ? "" : "?"}: ${tsType(parameterObject(queryParameters))};`,
    );
  }
  if (requestBody) typeMembers.push(`requestBody: ${tsType(requestBody)};`);
  const responseMembers = Object.entries(operation.responses ?? {}).map(
    ([status, result]) => {
      const schema = result.content?.["application/json"]?.schema;
      return `${JSON.stringify(status)}: ${schema ? tsType(schema) : "void"};`;
    },
  );
  typeMembers.push(`responses: { ${responseMembers.join(" ")} };`);
  lines.push(
    `  ${JSON.stringify(id)}: {\n${typeMembers.map((member) => `    ${member}`).join("\n")}\n  };`,
  );
}

lines.push(
  "}",
  "",
  "export type FetchResponse = { ok: boolean; status: number; json(): Promise<unknown> };",
);
lines.push(
  "export type FetchLike = (input: string, init?: { method: string; headers?: Record<string, string>; body?: string }) => Promise<FetchResponse>;",
  "",
  "export class ApiError extends Error {",
  '  constructor(public readonly status: number, public readonly body?: components["schemas"]["ErrorResponse"]) {',
  "    super(body?.message ?? `Request failed with status ${status}`);",
  '    this.name = "ApiError";',
  "  }",
  "}",
  "",
  "export class HealthApiClient {",
  "  private readonly baseUrl: string;",
  "  private readonly fetcher: FetchLike;",
  "",
  "  constructor(baseUrl: string, fetcher: FetchLike = globalThis.fetch as FetchLike) {",
  '    this.baseUrl = baseUrl.replace(/\\/+$/, "");',
  "    this.fetcher = fetcher;",
  "  }",
  "",
);

function requestArguments(route, params, hasQuery, hasBody) {
  let rendered = JSON.stringify(route);
  for (const parameter of params) {
    rendered = rendered.replace(
      `{${parameter.name}}`,
      `\${encodeURIComponent(path.${parameter.name})}`,
    );
  }
  const pathExpr = `\`${rendered.slice(1, -1)}\``;
  const queryExpr = hasQuery ? "query" : "undefined";
  const bodyExpr = hasBody ? "requestBody" : "undefined";
  return { pathExpr, queryExpr, bodyExpr };
}

for (const { route, method, operation } of operations) {
  const id = operation.operationId;
  const pathParameters = parametersFor(operation, "path");
  const queryParameters = parametersFor(operation, "query");
  const hasBody = Boolean(
    operation.requestBody?.content?.["application/json"]?.schema,
  );
  const response = successSchema(operation);
  const args = [];
  if (pathParameters.length)
    args.push(`path: operations[${JSON.stringify(id)}]["path"]`);
  if (hasBody)
    args.push(`requestBody: operations[${JSON.stringify(id)}]["requestBody"]`);
  if (queryParameters.length) {
    const required = queryParameters.some((parameter) => parameter.required);
    args.push(
      `query${required ? "" : "?"}: operations[${JSON.stringify(id)}]["query"]`,
    );
  }
  const returnType = response ? tsType(response) : "void";
  const { pathExpr, queryExpr, bodyExpr } = requestArguments(
    route,
    pathParameters,
    queryParameters.length > 0,
    hasBody,
  );
  const methodArgs = args.length ? args.join(", ") : "";
  lines.push(
    `  async ${id}(${methodArgs}): Promise<${returnType}> {`,
    `    return this.request<${returnType}>(${JSON.stringify(method)}, ${pathExpr}, ${queryExpr}, ${bodyExpr});`,
    "  }",
    "",
  );
}

lines.push(
  "  private async request<T>(method: string, path: string, query?: object, body?: unknown): Promise<T> {",
  "    const params = new URLSearchParams();",
  "    if (query) {",
  "      for (const [key, value] of Object.entries(query)) {",
  "        if (value !== undefined && value !== null) params.set(key, String(value));",
  "      }",
  "    }",
  "    const serialized = params.toString();",
  '    const suffix = serialized ? `?${serialized}` : "";',
  "    const response = await this.fetcher(`${this.baseUrl}${path}${suffix}`, {",
  "      method,",
  '      ...(body === undefined ? {} : { headers: { "content-type": "application/json" }, body: JSON.stringify(body) }),',
  "    });",
  "    const payload = await response.json().catch((error: unknown) => { if (error instanceof SyntaxError) return undefined; throw error; });",
  '    if (!response.ok) throw new ApiError(response.status, payload as components["schemas"]["ErrorResponse"] | undefined);',
  "    return payload as T;",
  "  }",
  "}",
  "",
  "export { HealthApiClient as ProfileApiClient };",
  "",
);

writeFileSync(
  outputPath,
  await format(lines.join("\n"), { filepath: outputPath }),
  "utf8",
);
