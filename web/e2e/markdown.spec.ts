import { expect, test } from "@playwright/test";
import { markdownToHtml } from "../src/markdown";

// show notes typed by hand: a table becomes list lines (item 26), also without outer pipes, and a
// "\|" stays a pipe inside its cell (full scan 2026-10-18)
test("show-notes Markdown: tables become list lines", () => {
  expect(markdownToHtml("| 片名 | 说明 |\n|---|---|\n| 《A\\|B》 | 好看 |")).toBe("<ul><li>《A|B》：好看</li></ul>");
  expect(markdownToHtml("片名 | 说明\n--- | ---\n《一部电影》 | 结尾")).toBe("<ul><li>《一部电影》：结尾</li></ul>");
  expect(markdownToHtml("Leon | Pei\n---")).toBe("<p>Leon | Pei</p>\n<hr>");
});
