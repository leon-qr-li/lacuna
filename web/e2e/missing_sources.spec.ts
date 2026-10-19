import { expect, test } from "@playwright/test";

// An episode whose recordings are not on the server (moved from the desktop with its raw tracks left on
// the computer): the page says which files are missing and takes them back (lacuna_app/sources.py; the
// server side is covered by tests/app/test_missing_sources.py, here the page is driven by routed answers).
const ID = "EP_TEST_合成";
const EP = `/api/episodes/${encodeURIComponent(ID)}`;
const MISSING = [
  { media_id: "sha256:aa", track: "Leon", file: "Leon_resident_evil.wav", duration: 3720.5 },
  { media_id: "sha256:bb", track: "Pei", file: "Pei_resident_evil.wav", duration: 3720.6 },
];

test("missing recordings: named on the episode page, uploaded back", async ({ page }) => {
  let left = [...MISSING];
  const sent: string[] = [];
  await page.route((u) => u.pathname === EP, async (route) => {
    const res = await route.fetch();
    await route.fulfill({ response: res, json: { ...(await res.json()), missing_sources: left } });
  });
  await page.route((u) => u.pathname === `${EP}/sources`, async (route) => {
    const name = new URL(route.request().url()).searchParams.get("name") ?? "";
    sent.push(name);
    if (name === "other.wav")
      return route.fulfill({ status: 422, json: { detail: "other.wav 不是这一集缺的原始音轨（内容对不上）。请选当初导入这一集用的那个文件。" } });
    left = left.filter((m) => m.file !== name);
    const ep = await (await page.request.get(EP)).json();
    await route.fulfill({ json: { filled: MISSING.find((m) => m.file === name), episode: { ...ep, missing_sources: left } } });
  });

  await page.goto(`/#/ep/${encodeURIComponent(ID)}/listen`);
  const banner = page.getByTestId("missing-sources");
  await expect(banner).toContainText("原始音轨不在服务器上");
  await expect(banner).toContainText("Leon_resident_evil.wav");
  await expect(banner).toContainText("Pei_resident_evil.wav");

  // a wrong file is refused with the server's words; the banner stays
  await page.getByTestId("missing-sources-input").setInputFiles([{ name: "other.wav", mimeType: "audio/wav", buffer: Buffer.from("RIFF") }]);
  await expect(banner).toContainText("不是这一集缺的原始音轨");

  // both originals: the page starts afresh and the banner is gone
  const reload = page.waitForEvent("load");
  await page.getByTestId("missing-sources-input").setInputFiles(
    MISSING.map((m) => ({ name: m.file, mimeType: "audio/wav", buffer: Buffer.from("RIFF") })),
  );
  await reload;
  expect(sent).toEqual(["other.wav", "Leon_resident_evil.wav", "Pei_resident_evil.wav"]);
  await expect(page.getByTestId("missing-sources")).toHaveCount(0);
  // the reloaded page may still be asking for the episode through the routes above
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

test("no banner when every recording is there", async ({ page }) => {
  await page.goto(`/#/ep/${encodeURIComponent(ID)}/listen`);
  await expect(page.getByTestId("main-audio")).toBeAttached();
  await expect(page.getByTestId("missing-sources")).toHaveCount(0);
  expect((await (await page.request.get(EP)).json()).missing_sources).toEqual([]);
});
