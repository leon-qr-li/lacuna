import { expect, test } from "@playwright/test";

// Several people in one episode (decision 2026-10-21-co-editing-safety-net), on the default server with
// two accounts: each sees the other in the header, a change by one shows up on the other's screen by
// itself, and Ctrl+Z only takes back your own steps.
const PW = "correct horse battery";
const EP = "EP_TEST_合成";
const API = `/api/episodes/${encodeURIComponent(EP)}`;

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

test("two people in one episode: presence, auto refresh, own undo", async ({ browser }) => {
  const lp = await (await browser.newContext()).newPage();
  expect((await lp.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW } })).ok()).toBeTruthy();
  const inv = await lp.request.post("/api/auth/invites", {
    data: { email: "pei@example.com", plan: "pro", space: "main", space_role: "editor" },
  });
  const link = (await inv.json()).link as string;
  const pp = await (await browser.newContext()).newPage();
  expect((await pp.request.post("/api/auth/register", { data: { invite: link.split("/").pop(), password: PW } })).ok()).toBeTruthy();

  await lp.goto(`/#/ep/${encodeURIComponent(EP)}/review`);
  await pp.goto(`/#/ep/${encodeURIComponent(EP)}/review`);
  await expect(lp.getByTestId("presence")).toHaveText("pei 也在这一集", { timeout: 12_000 });
  await expect(pp.getByTestId("presence")).toHaveText("leon 也在这一集", { timeout: 12_000 });

  // Pei restores the one cut waiting for review; Leon's screen follows by itself
  const before = await (await lp.request.get(API)).json();
  const cut = before.edits.find((e: { consequential: boolean }) => e.consequential);
  expect((await pp.request.post(`${API}/edits/${cut.id}/review`, { data: { action: "restore" } })).ok()).toBeTruthy();
  await expect(lp.getByRole("status").filter({ hasText: "这一集有新的修改，已更新为最新内容" })).toBeVisible({ timeout: 12_000 });

  // Leon's Ctrl+Z has nothing of his own to take back: Pei's step stays
  await lp.locator("body").click({ position: { x: 5, y: 5 } });
  await lp.keyboard.press("Control+z");
  const mid = await (await lp.request.get(API)).json();
  expect(mid.edits.find((e: { id: string }) => e.id === cut.id).status).toBe("restored");
  expect(mid.can_undo).toBe(false);
  expect((await (await pp.request.get(API)).json()).can_undo).toBe(true);

  // a decision from Leon's old version on the edit Pei changed is refused, not applied
  const stale = await lp.request.post(`${API}/edits/${cut.id}/review`, { data: { action: "keep", rev: before.rev } });
  expect(stale.status()).toBe(409);
  expect((await stale.json()).detail).toContain("pei");

  // Pei takes it back: the shared server is as it was
  expect((await pp.request.post(`${API}/undo`, { data: {} })).ok()).toBeTruthy();
  expect((await (await lp.request.get(API)).json()).edits.find((e: { id: string }) => e.id === cut.id).status).toBe("applied");
});
