import { expect, test } from "@playwright/test";
import { scan } from "./contrast-scan";

// 导入时核对专有名词 (lacuna_app/name_check.py): the episode's transcript card says how many names the import
// fixed; the list shows heard → written and what it is, and 「改回原样」 puts one back. The server side is tested in
// tests/app/test_name_check.py; here the list comes from a stub so the shared episode stays as it is.
const EP = "EP_TEST_合成";
const ROW = { wrong: "落兰", right: "诺兰", why: "导演克里斯托弗·诺兰", count: 3, places: [{ speaker: "Leon", start: 1.2, end: 3.0 }], state: "applied" };

for (const theme of ["light", "dark"] as const) {
  test(`names fixed at import are listed and can be put back (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/#/");
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
    let kept: unknown = null;
    await page.route("**/names", (r) => r.fulfill({ json: { rows: [ROW], on: true } }));
    await page.route("**/names/keep", async (r) => {
      kept = r.request().postDataJSON();
      const ep = await (await page.request.get(`/api/episodes/${encodeURIComponent(EP)}`)).json();
      await r.fulfill({ json: { ...ep, names: [{ ...ROW, state: "kept" }], changed: 3 } });
    });
    await page.goto(`/#/ep/${encodeURIComponent(EP)}/listen`);
    const chip = page.getByTestId("name-check-btn");
    await expect(chip).toHaveText(/专有名词已核对\s*1/);
    await chip.click();
    const pop = page.getByTestId("name-check-pop");
    await expect(pop).toContainText("落兰");
    await expect(pop).toContainText("诺兰");
    await expect(pop).toContainText("导演克里斯托弗·诺兰");
    await expect(pop).toContainText("共 3 处");
    expect((await scan(page)).bad).toEqual([]);
    await pop.getByTestId("name-check-keep").click();
    await expect(page.getByText("已改回「落兰」，以后也不再改")).toBeVisible();
    await expect(pop.getByText("已改回")).toBeVisible();
    expect(kept).toMatchObject({ wrong: "落兰", right: "诺兰" });
  });
}
