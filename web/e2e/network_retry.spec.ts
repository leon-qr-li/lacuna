import { expect, test, type Page } from "@playwright/test";

// Leon 2026-10-30: making a new show, the first 确认 said "Failed to fetch" and the second worked (on the cloud
// site the browser had kept a connection Cloudflare already dropped, net::ERR_QUIC_PROTOCOL_ERROR). A request
// that gets no answer at all is now tried once more by itself: one click is enough.
const PW = "correct horse battery";

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

/** The next `method` request to `path` dies without an answer, like a dropped connection; later ones go through. */
async function dropOnce(page: Page, method: string, path: string): Promise<() => number> {
  let calls = 0;
  await page.route(
    (u) => u.pathname === path,
    async (route) => {
      if (route.request().method() !== method) return route.fallback();
      calls += 1;
      if (calls === 1) return route.abort("failed");
      return route.fallback();
    },
  );
  return () => calls;
}

test("a dropped connection on 新节目 and its setup needs no second click", async ({ browser }) => {
  const leon = await (await browser.newContext()).newPage();
  expect((await leon.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW } })).ok()).toBeTruthy();
  const inv = await (await leon.request.post("/api/auth/invites", { data: { email: "retry@example.com", plan: "pro" } })).json();
  const p = await (await browser.newContext()).newPage();
  expect((await p.request.post("/api/auth/register", { data: { invite: inv.link.split("/").at(-1), password: PW } })).ok()).toBeTruthy();
  await p.goto("/");
  await p.getByTestId("welcome-own").click();

  // the setup of the show: language and hosts, then 开始使用 once
  const setup = p.getByTestId("show-setup");
  await expect(setup).toBeVisible();
  const saves = await dropOnce(p, "PUT", "/api/show");
  await setup.getByTestId("show-name").fill("周末电影院");
  await setup.getByLabel("第 1 位主持人的名字").fill("Ana");
  await setup.getByTestId("show-save").click();
  await expect(setup).toHaveCount(0);
  await expect(p.getByText("Failed to fetch")).toHaveCount(0);
  expect(saves()).toBe(2);

  // ＋ 新节目 → 建好节目 once: the new show opens, made only once
  const creates = await dropOnce(p, "POST", "/api/spaces");
  await p.getByTestId("project-menu").click();
  await p.getByTestId("project-new").click();
  await p.getByTestId("project-name").fill("片场夜谈");
  await p.getByTestId("project-create").click();
  await expect(p.getByTestId("project-menu")).toHaveText(/片场夜谈/);
  await expect(p.getByTestId("show-setup")).toContainText("介绍一下「片场夜谈」");
  expect(creates()).toBe(2);
  const mine = (await (await p.request.get("/api/spaces")).json()).mine as { name: string }[];
  expect(mine.filter((m) => m.name === "片场夜谈")).toHaveLength(1);
  await leon.close();
});
