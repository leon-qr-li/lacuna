import { expect, test } from "@playwright/test";

const EP = encodeURIComponent("EP_TEST_合成");

// one flow: the music tests share the backend's library and the episode's music
test("media library → credits → music on the episode → series rule", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "素材库" }).click();
  await expect(page).toHaveURL(/#\/library/);
  await expect(page.getByText("素材库还是空的")).toBeVisible();

  // add the theme: browse to the inbox folder, say what it is
  await page.getByRole("button", { name: "添加音乐文件" }).click();
  const fs = page.getByRole("dialog", { name: "选择音乐文件" });
  await fs.getByRole("button", { name: /music_inbox/ }).click();
  await fs.getByRole("button", { name: /odyssey_theme\.mp3/ }).click();
  const add = page.getByRole("dialog", { name: "加入素材库" });
  await add.getByLabel("备注").fill("这是奥德赛的主题曲");
  await add.getByRole("button", { name: "加入素材库" }).click();
  const theme = page.getByTestId("asset-row").filter({ hasText: "odyssey_theme.mp3" });
  await expect(theme).toContainText("待确认"); // from the file's own tags
  await expect(theme.getByTestId("credit-line")).toContainText("Odyssey Main Theme");

  // Claude looks up the official title (fake client), Leon confirms it
  await theme.getByRole("button", { name: "让 Claude 查正式曲名" }).click();
  await expect(theme.getByTestId("credit-line")).toContainText("《奥德赛》原声 · Ludwig Göransson — “Odysseus”");
  await expect(theme).toContainText("Claude 查的");
  await theme.getByRole("button", { name: "对，就是这首" }).click();
  await expect(theme).toContainText("已确认");

  // the jingle goes in as a series intro, with a hand-written credit
  await page.getByRole("button", { name: "添加音乐文件" }).click();
  await page.getByRole("dialog", { name: "选择音乐文件" }).getByRole("button", { name: /music_inbox/ }).click();
  await page.getByRole("dialog", { name: "选择音乐文件" }).getByRole("button", { name: /洛城片头\.wav/ }).click();
  await page.getByRole("dialog", { name: "加入素材库" }).locator("select").selectOption("jingle");
  await page.getByRole("dialog", { name: "加入素材库" }).getByRole("button", { name: "加入素材库" }).click();
  const jingle = page.getByTestId("asset-row").filter({ hasText: "洛城片头.wav" });
  await expect(jingle).toContainText("系列片头 / 片尾");
  await expect(jingle).toContainText("还不知道曲名");
  await jingle.getByRole("button", { name: "手动改" }).click();
  await jingle.getByLabel("曲名").fill("洛城二三事 片头");
  await jingle.getByRole("button", { name: "保存署名" }).click();
  await expect(jingle.getByTestId("credit-line")).toContainText("“洛城二三事 片头”");
  await expect(jingle).toContainText("已确认");

  // ---- the episode's music tab
  await page.goto(`/#/ep/${EP}/music`);
  await expect(page.getByRole("heading", { name: "配乐", exact: true })).toBeVisible();
  await expect(page.getByText("BGM：未设置")).toBeVisible();
  const voice = await page.getByText(/人声剪辑 .* → 成品 /).innerText();
  await page.getByLabel("选择素材").selectOption({ label: "“洛城二三事 片头”（洛城片头.wav）" });
  await page.getByLabel("用途").selectOption("intro");
  await page.getByRole("button", { name: "放进去" }).click();
  await expect(page.getByTestId("placement")).toHaveCount(1);
  await expect(page.getByText(/人声剪辑 .* → 成品 /)).not.toHaveText(voice); // the intro adds time

  // an interlude at 0:20 of the final cut
  await page.getByLabel("选择素材").selectOption({ label: "《奥德赛》原声 · Ludwig Göransson — “Odysseus”（odyssey_theme.mp3）" });
  await page.getByLabel("用途").selectOption("interlude");
  await page.getByRole("button", { name: "放进去" }).click();
  await expect(page.getByText("请写位置")).toBeVisible();
  await page.getByLabel("位置", { exact: true }).fill("0:20");
  await page.getByRole("button", { name: "放进去" }).click();
  const mid = page.getByTestId("placement").filter({ hasText: "间奏" });
  await expect(mid).toContainText("odyssey_theme.mp3");
  await expect(mid).toContainText("插入");
  const credits = page.getByTestId("credits");
  await expect(credits).toContainText("片头：“洛城二三事 片头”");
  await expect(credits).toContainText("间奏：《奥德赛》原声 · Ludwig Göransson — “Odysseus”");

  // hear the transition, then the whole mix stream
  await mid.getByRole("button", { name: "试听这一处" }).click();
  await expect(mid.getByRole("button", { name: "停止" })).toBeVisible();
  await expect.poll(() => page.getByTestId("placement-audio").evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(0.2);
  await mid.getByRole("button", { name: "停止" }).click();
  const mixUrl = await page.getByTestId("mix-audio").getAttribute("src");
  expect(mixUrl).toMatch(/\/mix\/[0-9a-f]+\.wav$/);
  const head = await page.request.get(mixUrl!, { headers: { Range: "bytes=0-43" } });
  expect(head.status()).toBe(206);

  // gain change is saved
  await mid.getByLabel("音量（dB）").fill("-4");
  await mid.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText("已保存")).toBeVisible();

  // remember the intro as the series rule, then it is offered once the episode has none
  await page.getByRole("button", { name: "记成系列片头片尾" }).click();
  await expect(page.getByText("已记住")).toBeVisible();
  await page.getByTestId("placement").filter({ hasText: "片头" }).getByRole("button", { name: "去掉" }).click();
  await expect(page.getByTestId("series-suggestion")).toContainText("洛城二三事");
  await page.getByRole("button", { name: "用系列片头片尾" }).click();
  await expect(page.getByTestId("placement").filter({ hasText: "片头" })).toHaveCount(1);
  await expect(page.getByTestId("series-suggestion")).toHaveCount(0);

  // leave the shared episode as it was
  for (const name of ["片头", "间奏"]) {
    await page.getByTestId("placement").filter({ hasText: name }).getByRole("button", { name: "去掉" }).click();
  }
  await page.getByRole("button", { name: "这一集不用" }).click();
  await expect(page.getByTestId("placement")).toHaveCount(0);
});
