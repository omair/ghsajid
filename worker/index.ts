import postmap from "./postmap.json";

interface Env {
  ASSETS: Fetcher;
}

/**
 * WordPress served plain permalinks (/?p=123) — confirmed against the live
 * site, which used no pretty permalinks at all. Those URLs are what Rekhta,
 * Facebook and the literary blogs link to.
 *
 * They cannot be expressed as static redirect rules: every one of them is the
 * path "/" with a query string, and Cloudflare's redirect matching ignores
 * query strings. So the lookup happens here, ahead of asset serving.
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const postId = url.searchParams.get("p");

    if (postId) {
      const destination = (postmap as Record<string, string>)[postId];
      if (destination) {
        return Response.redirect(
          new URL(destination, url.origin).toString(),
          301,
        );
      }
    }

    return env.ASSETS.fetch(request);
  },
};
