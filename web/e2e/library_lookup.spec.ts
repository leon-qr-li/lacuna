import { expect, test } from "@playwright/test";

// 素材库: two title lookups at the same time (backlog item 14). Each row keeps its own "正在查" state
// and both get their result, whichever finishes first. The fake (tests/app/fake_credit.py) answers
// "并发 A 慢" after 1.5 s and "并发 B" after 0.5 s, so B finishes while A is still looking.

function wav(hz: number, rate = 8000) {
  const n = rate, b = Buffer.alloc(44 + n * 2);
  b.write("RIFF", 0); b.writeUInt32LE(36 + n * 2, 4); b.write("WAVEfmt ", 8); b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22); b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate * 2, 28);
  b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34); b.write("data", 36); b.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) b.writeInt16LE(Math.round(3000 * Math.sin((i / rate) * 2 * Math.PI * hz)), 44 + i * 2);
  return b;
}

test("two title lookups at once both come back", async ({ page }) => {
  const ids: string[] = [];
  for (const [name, note, hz] of [["lookup_a.wav", "并发 A 慢", 330], ["lookup_b.wav", "并发 B", 550]] as const) {
    const r = await page.request.post(`/api/library/upload?name=${name}&kind=other&note=${encodeURIComponent(note)}`, {
      headers: { "content-type": "application/octet-stream" }, data: wav(hz),
    });
    expect(r.ok()).toBe(true);
    ids.push((await r.json()).asset.id);
  }
  await page.goto("/#/library");
  const a = page.getByTestId("asset-row").filter({ hasText: "lookup_a.wav" });
  const b = page.getByTestId("asset-row").filter({ hasText: "lookup_b.wav" });

  await a.getByRole("button", { name: "让 LACUNA 查正式曲名" }).click();
  await b.getByRole("button", { name: "让 LACUNA 查正式曲名" }).click();
  // both looking at the same time
  await expect(a.getByRole("button", { name: "LACUNA 正在查…" })).toBeVisible();
  await expect(b.getByRole("button", { name: "LACUNA 正在查…" })).toBeVisible();

  // B first; A is still looking and keeps its state
  await expect(b.getByTestId("credit-line")).toContainText("Concurrent Theme B");
  await expect(a.getByRole("button", { name: "LACUNA 正在查…" })).toBeVisible();
  // then A, and B's result is still there
  await expect(a.getByTestId("credit-line")).toContainText("Concurrent Theme A", { timeout: 5_000 });
  await expect(b.getByTestId("credit-line")).toContainText("Concurrent Theme B");
  await expect(a).toContainText("LACUNA 查的");
  await expect(b).toContainText("LACUNA 查的");

  // and both were saved: a fresh load shows both
  await page.reload();
  await expect(page.getByTestId("asset-row").filter({ hasText: "lookup_a.wav" }).getByTestId("credit-line")).toContainText("Concurrent Theme A");
  await expect(page.getByTestId("asset-row").filter({ hasText: "lookup_b.wav" }).getByTestId("credit-line")).toContainText("Concurrent Theme B");

  for (const id of ids) expect((await page.request.delete(`/api/library/assets/${id}`)).ok()).toBe(true);
});
