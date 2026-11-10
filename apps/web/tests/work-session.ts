import { expect, type BrowserContext, type Page } from "@playwright/test";

// Reuse real authenticated sessions within this test worker. Keeping cookies in
// memory avoids repeated logins exhausting the unchanged production source cap.
const sessions = new Map<string, {
  cookies: Awaited<ReturnType<BrowserContext["cookies"]>>;
  user: { id: string };
}>();

export async function loginWork(page: Page, kind: string) {
  const saved = sessions.get(kind);
  if (saved) {
    await page.context().addCookies(saved.cookies);
    const me = await page.request.get("/api/v1/auth/me");
    expect(me.status()).toBe(200);
    return saved.user;
  }
  const response = await page.request.post("/api/v1/auth/sessions", { data: {
    email: process.env[`ALTVIA_E2E_WORK_${kind}_EMAIL`]!,
    password: process.env[`ALTVIA_E2E_WORK_${kind}_PASSWORD`]!,
  }, headers: { Origin: "https://127.0.0.1:3443" } });
  expect(response.status()).toBe(201);
  const user: { id: string } = (await response.json()).user;
  sessions.set(kind, { cookies: await page.context().cookies(), user });
  return user;
}
