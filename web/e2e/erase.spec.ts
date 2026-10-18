import { expect, test } from "@playwright/test";

// backlog item 8: a single-track erase in the AI first cut is filled with room tone and shows on that lane only
test.use({ baseURL: "http://127.0.0.1:8798" });

test("one host erased: room tone, on Pei's lane only, timeline unchanged", async ({ page, request }) => {
  const eps = await (await request.get("/api/episodes")).json();
  const id = eps.episodes[0].id;
  const ep = await (await request.get(`/api/episodes/${id}`)).json();
  const erase = ep.edits.find((e: { room_tone?: boolean }) => e.room_tone);
  expect(erase.tracks).toEqual(["Pei"]);
  // before and after are the same length: nothing on the timeline moved
  const ab = await (await request.get(`/api/episodes/${id}/edits/${erase.id}/ab`)).json();
  expect(ab.after.duration).toBeCloseTo(ab.before.duration, 2);

  await page.goto("/");
  await page.getByRole("link", { name: /整集试听/ }).click();
  await expect(page.getByTestId("lane-Pei").locator(`.mark-span[title="${erase.title}"]`)).toHaveCount(1);
  await expect(page.getByTestId("lane-Leon").locator(`.mark-span[title="${erase.title}"]`)).toHaveCount(0);
});
