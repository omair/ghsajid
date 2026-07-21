import postmap from "./_postmap.json";

/**
 * WordPress served plain permalinks (/?p=123) — confirmed against the live
 * site, which uses no pretty permalinks at all. Cloudflare's _redirects file
 * matches paths only, never query strings, so old inbound links from Rekhta,
 * Facebook and literary blogs are handled here instead.
 */
export const onRequest: PagesFunction = async (context) => {
  const url = new URL(context.request.url);
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

  return context.next();
};
