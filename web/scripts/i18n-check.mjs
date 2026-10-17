// Interface-language check (run by `npm run build`): every Chinese string in web/src must be the
// literal first argument of t(...), and every such key needs English in src/i18n/en.ts or
// src/features/<name>/en.ts. A line ending in `// i18n-ignore` is skipped (data, not UI text).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
const HAN = /[㐀-鿿]/;
// files not migrated yet (they still show Chinese in the English interface)
const PENDING = new Set([
]);

const files = [];
(function walk(d) {
  for (const f of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, f.name);
    if (f.isDirectory()) walk(p);
    else if (/\.tsx?$/.test(f.name) && !f.name.endsWith(".d.ts")) files.push(p);
  }
})(SRC);

const rel = (p) => path.relative(SRC, p).split(path.sep).join("/");
const isDict = (p) => path.basename(p) === "en.ts";
const parse = (p) => ts.createSourceFile(p, fs.readFileSync(p, "utf8"), ts.ScriptTarget.Latest, true, p.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);

const english = new Map(); // key -> dictionary file
for (const p of files.filter(isDict)) {
  const sf = parse(p);
  sf.forEachChild(function visit(n) {
    if (ts.isPropertyAssignment(n) && n.parent && ts.isObjectLiteralExpression(n.parent) && ts.isVariableDeclaration(n.parent.parent)) {
      const k = n.name;
      if (ts.isStringLiteral(k) || ts.isIdentifier(k)) english.set(k.text, rel(p));
    }
    n.forEachChild(visit);
  });
}

const problems = [];
const used = new Set();
for (const p of files) {
  if (isDict(p) || rel(p) === "i18n/index.ts") continue;
  const sf = parse(p);
  const lines = sf.text.split("\n");
  const where = (n) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line;
  const ignored = (n) => /\/\/\s*i18n-ignore\s*$/.test(lines[where(n)]);
  const isTKey = (n) => {
    const c = n.parent;
    return c && ts.isCallExpression(c) && c.arguments[0] === n && ts.isIdentifier(c.expression) && c.expression.text === "t";
  };
  const report = (n, msg) => problems.push(`${rel(p)}:${where(n) + 1}: ${msg}`);
  sf.forEachChild(function visit(n) {
    let text = null;
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) text = n.text;
    else if (ts.isJsxText(n)) text = n.text;
    else if (ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) text = n.text;
    if (text !== null && HAN.test(text)) {
      if ((ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) && isTKey(n)) {
        used.add(n.text);
        if (!english.has(n.text)) report(n, `no English for t(${JSON.stringify(n.text)})`);
      } else if (!PENDING.has(rel(p)) && !ignored(n)) {
        report(n, `Chinese outside t(): ${JSON.stringify(text.trim().slice(0, 60))}`);
      }
    }
    n.forEachChild(visit);
  });
}

const unused = [...english.keys()].filter((k) => !used.has(k));
if (unused.length) console.warn(`i18n: ${unused.length} English entries no longer used:\n  ` + unused.map((k) => `${english.get(k)}: ${JSON.stringify(k)}`).join("\n  "));
if (problems.length) {
  console.error(`i18n: ${problems.length} problem(s):\n  ` + problems.join("\n  "));
  process.exit(1);
}
console.log(`i18n: ok (${used.size} strings, ${PENDING.size} files pending)`);
