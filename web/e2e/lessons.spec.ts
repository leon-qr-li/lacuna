import { expect, test, type Page } from "@playwright/test";
import { undoKey } from "./undo";

// 本集学到的规则 (首次检测 #12): a step between 整集试听 and 配乐; LACUNA proposes this episode's habits with
// evidence, Leon adopts, edits by hand, tells LACUNA how to change, or skips each. Rules come from a scripted
// writer (tests/app/fake_lessons.py).
test.use({ baseURL: "http://127.0.0.1:8798" });

const SHOTS = process.env.LESSONS_SHOTS; // folder for review screenshots (optional)

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

test("本集学到的规则: summary with evidence → adopt / edit / tell LACUNA / skip", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  await page.getByLabel(/对 LACUNA ?说/).fill("这段跑题了删掉");
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByTestId("proposal").getByRole("button", { name: "批准" }).click(); // a review decision too
  await expect(page.getByText(/已批准并应用/)).toBeVisible();

  // not a step of the flow (Q8A): reached from 整集试听 by its link
  const steps = page.getByRole("navigation", { name: "制作流程" }).getByRole("link");
  await expect(steps.filter({ hasText: "本集学到的规则" })).toHaveCount(0);
  await page.getByTestId("lessons-link").click();
  await expect(page).toHaveURL(/\/lessons$/);
  const lessonsUrl = page.url();

  const view = page.getByTestId("lessons");
  await expect(view.getByRole("heading", { name: "本集学到的规则" })).toBeVisible();
  // nothing runs by itself (Leon 2026-10-18): the page explains, he clicks 总结
  await expect(view).toContainText("如果这一集已经剪完了，请点「总结」");
  await page.waitForTimeout(600);
  await expect(page.getByTestId("waiting")).toHaveCount(0);
  await expect(view.getByTestId("lesson")).toHaveCount(0);
  await view.getByTestId("lessons-run").click();
  await expect(page.getByTestId("waiting")).toBeVisible();
  const cards = view.getByTestId("lesson");
  await expect(cards.first()).toBeVisible();
  const digress = cards.filter({ hasText: "Leon 跑题的段落剪狠一点" });
  await expect(digress).toContainText("新规则");
  await expect(digress).toContainText(/你在第 \d+ 句让我删了一段跑题的话/);
  await digress.getByText(/依据/).click();
  await expect(digress).toContainText("你说：「这段跑题了删掉」");
  await shot(page, "lessons_light");

  await digress.getByRole("button", { name: "采用", exact: true }).click();
  await expect(digress).toContainText("已采用，已生效");
  await expect(view.getByRole("list", { name: "已处理" })).toContainText("Leon 跑题的段落剪狠一点");

  // edit by hand, then tell LACUNA, then skip and reconsider
  const pause = cards.filter({ hasText: "这一集 AI 收紧的停顿你都保留了" }); // its evidence line stays while editing
  await expect(pause.getByTestId("lesson-title")).toHaveText("长停顿收到 0.4 秒");
  await pause.getByRole("button", { name: "直接改" }).click();
  await pause.getByLabel("规则怎么写").fill("长停顿收到 0.5 秒");
  await pause.getByRole("button", { name: "保存" }).click();
  const edited = pause;
  await expect(edited.getByTestId("lesson-title")).toHaveText("长停顿收到 0.5 秒");
  await expect(edited).toContainText("改过");
  await edited.getByRole("button", { name: "跟 LACUNA 说怎么改" }).click();
  await edited.getByRole("textbox", { name: "告诉 LACUNA 这条规则要怎么改" }).fill("只对 Leon");
  await edited.getByRole("button", { name: "发给 LACUNA" }).click();
  await expect(edited.getByTestId("lesson-title")).toHaveText("长停顿收到 0.5 秒（只对 Leon）");
  await expect(edited).toContainText("我按你说的改了：只对 Leon。");
  await edited.getByRole("button", { name: "跳过" }).click();
  await expect(edited).toContainText("已跳过");
  await edited.getByRole("button", { name: "重新考虑" }).click();
  await expect(edited.getByRole("button", { name: "采用", exact: true })).toBeVisible();

  // more chat afterwards: the summary says so and can run again; decided lessons stay
  await page.goto(page.url().replace(/\/lessons$/, "/listen"));
  await page.getByLabel(/对 LACUNA ?说/).fill("停顿短一点");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByTestId("proposal").last()).toBeVisible();
  await page.goto(page.url().replace(/\/listen$/, "/lessons"));
  await expect(view).toContainText("这之后又有新的对话或审阅");
  await view.getByTestId("lessons-rerun").click();
  await expect(view.getByRole("list", { name: "已处理" })).toContainText("Leon 跑题的段落剪狠一点");
  await expect(view).not.toContainText("这之后又有新的对话或审阅");

  // the adopted lesson is an active rule on 学到的规则
  await page.goto("/#/learning");
  await page.getByRole("tab", { name: /已生效/ }).click();
  const rule = page.getByTestId("rule").filter({ hasText: "Leon 跑题的段落剪狠一点" });
  await expect(rule).toContainText("你在「本集学到的规则」里确认的");
  await expect(rule).toContainText("已生效");

  // dark theme and English, for review
  await page.goto(lessonsUrl);
  await expect(cards.first()).toBeVisible();
  await page.evaluate(() => localStorage.setItem("lacuna.theme", "dark"));
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(cards.first()).toBeVisible();
  await shot(page, "lessons_dark");
  await page.evaluate(() => localStorage.removeItem("lacuna.theme"));

  // other specs share this backend: take the approved chat edit back out of the review list
  await page.goto(lessonsUrl.replace(/\/lessons$/, "/listen"));
  await expect(page.getByTestId("play")).toBeVisible();
  await undoKey(page);
  await expect(page.locator(".toast")).toContainText("已撤销：批准");
});

test("本集学到的规则 in English fits the layout", async ({ page, context }) => {
  await context.addCookies([{ name: "lacuna_lang", value: "en", url: "http://127.0.0.1:8798" }]);
  await page.addInitScript(() => localStorage.setItem("lacuna.lang", "en"));
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  await page.goto(page.url().replace(/\/listen$/, "/lessons"));
  const view = page.getByTestId("lessons");
  await expect(view.getByRole("heading", { name: "Rules from this episode" })).toBeVisible();
  const run = view.getByTestId("lessons-run"); // the other spec may have summarized already
  await expect(run.or(view.getByTestId("lesson").first())).toBeVisible();
  if (await run.isVisible()) await run.click();
  await expect(view.getByTestId("lesson").first()).toBeVisible();
  await expect(view.getByRole("button", { name: "Tell LACUNA" }).first()).toBeVisible();
  // no button text wraps or overflows its card
  const overflow = await view.evaluate((el) =>
    [...el.querySelectorAll("button")].filter((b) => b.scrollWidth > b.clientWidth + 1).map((b) => b.textContent),
  );
  expect(overflow).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await shot(page, "lessons_en");
});
