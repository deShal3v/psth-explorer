/**
 * Collector for the in-app interaction events that index.dc.html sends via track().
 *
 * Traffic analytics (pageviews, referrers, countries, devices) does NOT need this --
 * turn on Cloudflare Web Analytics for the Pages project and it is injected for you.
 * This Worker exists for the other half of the question: what people actually do once
 * they are in the app. Which participant they open, which arrays and conditions they
 * look at, whether they hit play.
 *
 * Deploy:
 *   npx wrangler deploy                       # from this directory, with wrangler.toml
 * then point the site at it:
 *   window.NSE_ANALYTICS_URL = "https://nse-analytics.<subdomain>.workers.dev"
 *
 * Query it later in the dashboard (Workers > Analytics Engine) with SQL, e.g.
 *   SELECT blob1 AS event, blob2 AS user, count() FROM nse_events
 *   WHERE timestamp > now() - INTERVAL '7' DAY GROUP BY event, user ORDER BY count() DESC
 *
 * Privacy: no cookies and no stored IP. `sid` is a per-tab random string generated in
 * the browser and lost when the tab closes, which is enough to tell one visit's actions
 * apart without identifying a person. Country comes from Cloudflare's edge, not the page.
 */

const ALLOW = ["https://psth.io", "https://www.psth.io"];

const cors = origin => ({
  "Access-Control-Allow-Origin": ALLOW.includes(origin) ? origin : ALLOW[0],
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
});

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(origin) });
    if (request.method !== "POST") return new Response("POST only", { status: 405, headers: cors(origin) });

    let e;
    try { e = await request.json(); } catch { return new Response("bad json", { status: 400, headers: cors(origin) }); }
    if (!e || typeof e.event !== "string" || e.event.length > 32) {
      return new Response("bad event", { status: 400, headers: cors(origin) });
    }

    const s = (v, n = 64) => (v == null ? "" : String(v).slice(0, n));
    env.NSE_EVENTS?.writeDataPoint({
      // blobs are the dimensions you group by; doubles are the numbers you aggregate
      blobs: [
        s(e.event, 32),                                  // load | participant | array | condition | view | play
        s(e.user, 8),                                    // t5 | t12 | t15 | t16 | t17
        s(e.array || e.cond || e.mode, 32),              // whichever the event carries
        s(e.sid, 24),                                    // per-tab id, not a person
        s(request.cf?.country, 4),
        s(e.ref || "", 128),                             // referrer, page-supplied
      ],
      doubles: [Number(e.sweep) || 0, Number(e.w) || 0, Number(e.h) || 0],
      indexes: [s(e.event, 32)],
    });

    return new Response(null, { status: 204, headers: cors(origin) });
  },
};
