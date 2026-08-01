/**
 * POST /collect -- collector for the in-app interaction events that track() sends.
 *
 * This is a Pages Function, so it is deployed with the site and lives on the same
 * origin. That means no workers.dev subdomain, no CORS, and no third-party request
 * for an ad blocker to object to.
 *
 * Traffic analytics (pageviews, referrers, countries, devices) does NOT come from
 * here. Turn on Cloudflare Web Analytics for the Pages project and it is injected
 * automatically. This endpoint answers the other half: what people do once they
 * arrive, which participant they open, which arrays and conditions they look at,
 * whether they press play.
 *
 * Requires an Analytics Engine binding named NSE_EVENTS pointing at the `psth` dataset.
 * Query it in the dashboard under Workers > Analytics Engine, for example:
 *   SELECT blob1 AS event, blob2 AS participant, count() AS n
 *   FROM psth WHERE timestamp > now() - INTERVAL '7' DAY
 *   GROUP BY event, participant ORDER BY n DESC
 *
 * Privacy: no cookies, no stored IP. `sid` is a random per-tab string made in the
 * browser and lost when the tab closes, enough to separate one visit's actions
 * without identifying a person. Country is added by the Cloudflare edge.
 */

const s = (v, n = 64) => (v == null ? "" : String(v).slice(0, n));

export async function onRequestPost({ request, env }) {
  let e;
  try { e = await request.json(); } catch { return new Response("bad json", { status: 400 }); }
  if (!e || typeof e.event !== "string" || e.event.length > 32) {
    return new Response("bad event", { status: 400 });
  }

  // No binding (local dev, or not configured yet) should not surface as a client error.
  if (!env.NSE_EVENTS) return new Response(null, { status: 204 });

  env.NSE_EVENTS.writeDataPoint({
    // blobs are the dimensions you group by; doubles are the numbers you aggregate
    blobs: [
      s(e.event, 32),                       // load | participant | array | condition | view | play
      s(e.user, 8),                         // t5 | t12 | t15 | t16 | t17
      s(e.array || e.cond || e.mode, 32),   // whichever the event carries
      s(e.sid, 24),                         // per-tab id, not a person
      s(request.cf?.country, 4),
      s(e.ref, 128),                        // referrer, page-supplied
    ],
    doubles: [Number(e.sweep) || 0, Number(e.w) || 0, Number(e.h) || 0],
    indexes: [s(e.event, 32)],
  });

  return new Response(null, { status: 204 });
}

export async function onRequestGet() {
  return new Response("POST only", { status: 405 });
}
