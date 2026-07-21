// @ts-check
import { unified } from "@astrojs/markdown-remark";
import { defineConfig } from "astro/config";
import remarkBreaks from "remark-breaks";

export default defineConfig({
  site: "https://ghsajid.com",
  markdown: {
    // Astro 7 defaults to the Sätteri processor, which has no hard-break
    // option. Verse depends on one: a single newline must render as <br>, or
    // markdown fuses both misra of every sher into one run-on line.
    processor: unified({
      remarkPlugins: [remarkBreaks],
      smartypants: false,
    }),
  },
});
