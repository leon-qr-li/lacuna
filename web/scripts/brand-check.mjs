// Brand check (run by `npm run build`, backlog item 28): no text in web/src may show the AI vendor's
// name to users. Every string literal, template part and JSX text is checked; comments are not.
// Internal values stay lowercase ("claude" as an editor id), so only the capitalised names count.
// The AI is called LACUNA in the interface; the key is "AI 密钥" / "AI key".
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.join(ROOT, "src");
export const VENDOR = /Claude|Anthropic|ANTHROPIC|sk-ant/;

const files = [];
(function walk(d) {
  for (const f of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, f.name);
    if (f.isDirectory()) walk(p);
    else if (/\.tsx?$/.test(f.name) && !f.name.endsWith(".d.ts")) files.push(p);
  }
})(SRC);

const rel = (p) => path.relative(ROOT, p).split(path.sep).join("/");
const problems = [];
for (const p of files) {
  const sf = ts.createSourceFile(p, fs.readFileSync(p, "utf8"), ts.ScriptTarget.Latest, true, p.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  sf.forEachChild(function visit(n) {
    let text = null;
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isJsxText(n)) text = n.text;
    else if (ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) text = n.text;
    if (text !== null && VENDOR.test(text)) {
      const line = sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
      problems.push(`${rel(p)}:${line}: ${JSON.stringify(text.trim().slice(0, 60))}`);
    }
    n.forEachChild(visit);
  });
}
for (const f of ["index.html"]) {
  const p = path.join(ROOT, f);
  if (fs.existsSync(p) && VENDOR.test(fs.readFileSync(p, "utf8"))) problems.push(`${f}: names the AI vendor`);
}

if (problems.length) {
  console.error("brand-check: users must never see Claude / Anthropic; call the AI LACUNA:\n  " + problems.join("\n  "));
  process.exit(1);
}
console.log(`brand-check: ${files.length} files, no vendor name in interface text`);
