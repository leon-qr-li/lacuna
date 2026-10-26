// k6 load test of a local LACUNA server built by make_site.py (scripts/loadtest/README.md).
//
//   k6 run -e SITE=/tmp/lt/site.json -e BASE=http://127.0.0.1:8790 -e PLAN=ramp scripts/loadtest/lacuna.js
//
// One virtual user = one signed-in person working on an episode the way the web page does it:
// open the site (page, bundle, status, shows, episodes), open the episode (document + the first
// stretch of audio), then for the rest of the session: the 5-second presence beat (useCoedit.ts),
// a review decision every ~15 s (the audio is fetched again from the playhead, since the version
// changed), an A/B listen of an edit now and then, the transcript window around the playhead.
// A few VUs instead watch an import (GET /api/imports every 1.5 s, ImportPanel.tsx).
// Never calls the AI, sends mail or touches anything outside the local server.
import http from "k6/http";
import exec from "k6/execution";
import { check, sleep } from "k6";
import { Trend, Counter, Rate } from "k6/metrics";

const SITE = JSON.parse(open(__ENV.SITE || "/tmp/lt/site.json"));
const BASE = __ENV.BASE || "http://127.0.0.1:8790";
const PLAN = __ENV.PLAN || "ramp";
const SESSION_S = Number(__ENV.SESSION_S || 600);     // one editing session, then the VU starts over
const people = SITE.people;
const REVIEW_S = Number(__ENV.REVIEW_S || 15);         // average seconds between review decisions
const AB_S = Number(__ENV.AB_S || 45);                 // ... between A/B listens
const IDLE = __ENV.IDLE === "1";                       // page open, nobody working: presence beat only

const tOpen = new Trend("t_open_site", true);
const tEpisode = new Trend("t_open_episode", true);
const tPresence = new Trend("t_presence", true);
const tReview = new Trend("t_review", true);
const tAudioFirst = new Trend("t_audio_first_chunk", true);
const tAB = new Trend("t_ab", true);
const tText = new Trend("t_transcript", true);
const tImports = new Trend("t_imports_poll", true);
const stale = new Counter("review_stale_409");
const bad = new Rate("bad_status");

// ramp: steady steps of online people; spike: sudden jump; soak: hold
const PLANS = {
  ramp: {
    editors: {
      executor: "ramping-vus", startVUs: 0, gracefulRampDown: "10s",
      stages: (__ENV.STEPS || "10,20,40,60,80,100,120,150").split(",").flatMap((n) => [
        { duration: "30s", target: Number(n) }, { duration: __ENV.HOLD || "90s", target: Number(n) }]),
    },
    importers: { executor: "constant-vus", vus: Number(__ENV.IMPORTERS || 3), duration: __ENV.IMPORT_FOR || "20m", exec: "importer" },
  },
  spike: {
    editors: { executor: "ramping-vus", startVUs: 0, stages: [
      { duration: "10s", target: Number(__ENV.SPIKE || 100) }, { duration: "2m", target: Number(__ENV.SPIKE || 100) },
      { duration: "10s", target: 0 }] },
  },
  soak: {
    editors: { executor: "constant-vus", vus: Number(__ENV.VUS || 40), duration: __ENV.FOR || "15m" },
    importers: { executor: "constant-vus", vus: 3, duration: __ENV.FOR || "15m", exec: "importer" },
  },
};

export const options = {
  scenarios: PLANS[PLAN],
  discardResponseBodies: false,
  thresholds: {
    bad_status: ["rate<0.01"],
    t_presence: ["p(95)<500"],
    t_review: ["p(95)<1500"],
  },
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "p(99)", "max"],
};

function person() {
  // VU n works as person n (wrapping round); a person invited to a shared show works there
  const p = people[(exec.vu.idInTest - 1) % people.length];
  const show = p.also || p.show;
  return { p, jar: { [SITE.cookie]: p.cookie, [SITE.space_cookie]: show } };
}

function get(url, params, tag) {
  const r = http.get(BASE + url, { ...params, tags: { name: tag } });
  bad.add(r.status >= 400 && r.status !== 409);
  return r;
}

function post(url, body, params, tag) {
  const r = http.post(BASE + url, JSON.stringify(body), {
    ...params, headers: { "Content-Type": "application/json", ...(params.headers || {}) }, tags: { name: tag } });
  bad.add(r.status >= 400 && r.status !== 409);
  return r;
}

let bundle = null;

function openSite(params) {
  const t0 = Date.now();
  const page = get("/", params, "page");
  if (bundle === null) {
    const m = page.body && page.body.match(/\/assets\/[^"]+\.js/);
    bundle = m ? m[0] : "";
  }
  if (bundle) http.get(BASE + bundle, { ...params, tags: { name: "bundle" }, responseType: "none" });
  for (const u of ["/api/auth/status", "/api/spaces", "/api/episodes", "/api/site/notice", "/api/app"]) get(u, params, u);
  tOpen.add(Date.now() - t0);
}

const AUDIO_CHUNK = 2 * 1024 * 1024;      // ~24 s of 44.1 kHz mono 16-bit

function audio(epUrl, version, at, params) {
  const first = 44 + Math.floor(at * 44100) * 2;
  const r = http.get(`${BASE}${epUrl}/audio/${version}.wav`, {
    ...params, headers: { Range: `bytes=${first}-${first + AUDIO_CHUNK - 1}` }, tags: { name: "audio" }, responseType: "none" });
  bad.add(r.status >= 400);
  tAudioFirst.add(r.timings.waiting);
  return r;
}

export default function () {
  const { p, jar } = person();
  const params = { cookies: jar };
  openSite(params);
  sleep(1 + Math.random() * 2);

  const epUrl = `/api/episodes/${encodeURIComponent(p.episode)}`;
  let r = get(epUrl, params, "episode");
  tEpisode.add(r.timings.duration);
  if (!check(r, { "episode opens": (x) => x.status === 200 })) { sleep(5); return; }
  let ep = r.json();
  const edits = ep.edits.filter((e) => e.consequential).map((e) => e.id);
  let at = Math.random() * Math.max(ep.duration - 120, 1);
  if (!IDLE) audio(epUrl, ep.version, at, params);

  const end = Date.now() + SESSION_S * 1000 * (0.7 + Math.random() * 0.6);
  const never = Date.now() + 1e12;
  let nextReview = IDLE ? never : Date.now() + REVIEW_S * 1000 * (0.5 + Math.random());
  let nextAB = IDLE ? never : Date.now() + AB_S * 1000 * (0.5 + Math.random());
  let nextText = IDLE ? never : Date.now() + 10000 + Math.random() * 20000;
  while (Date.now() < end) {
    sleep(5);
    at += 5;
    r = post(`${epUrl}/presence`, {}, params, "presence");
    tPresence.add(r.timings.duration);
    if (r.status === 200 && r.json().rev > ep.rev) {        // someone else changed it: load the latest
      const n = get(epUrl, params, "episode");
      if (n.status === 200) ep = n.json();
    }
    const now = Date.now();
    if (now >= nextReview && edits.length) {
      const eid = edits[Math.floor(Math.random() * edits.length)];
      const action = Math.random() < 0.5 ? "keep" : "restore";
      r = post(`${epUrl}/edits/${eid}/review`, { action, playhead: at, rev: ep.rev }, params, "review");
      tReview.add(r.timings.duration);
      if (r.status === 409) { stale.add(1); const n = get(epUrl, params, "episode"); if (n.status === 200) ep = n.json(); }
      else if (r.status === 200) { ep = r.json(); audio(epUrl, ep.version, at, params); }
      nextReview = now + REVIEW_S * 1000 * (0.67 + Math.random() * 0.67);
    }
    if (now >= nextAB && edits.length) {
      const eid = edits[Math.floor(Math.random() * edits.length)];
      const t0 = Date.now();
      r = get(`${epUrl}/edits/${eid}/ab`, params, "ab");
      if (r.status === 200) {
        const ab = r.json();
        for (const side of ["before", "after"]) http.get(BASE + ab[side].url, { ...params, tags: { name: "clip" }, responseType: "none" });
      }
      tAB.add(Date.now() - t0);
      nextAB = now + AB_S * 1000 * (0.67 + Math.random() * 0.67);
    }
    if (now >= nextText) {
      r = get(`${epUrl}/manual/transcript?t0=${Math.max(at - 60, 0).toFixed(1)}&t1=${(at + 60).toFixed(1)}&v=${ep.version}`, params, "transcript");
      tText.add(r.timings.duration);
      nextText = now + 20000 + Math.random() * 20000;
    }
    if (at > ep.duration - 30) at = 0;
  }
}

export function importer() {
  const { jar } = person();
  const r = get("/api/imports", { cookies: jar }, "imports");
  tImports.add(r.timings.duration);
  sleep(1.5);
}
