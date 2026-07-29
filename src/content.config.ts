import { glob } from "astro/loaders";
import { defineCollection, reference, z } from "astro:content";

const language = z.enum(["urdu", "punjabi", "english"]);
const script = z.enum([
  "nastaliq",
  "naskh",
  "shahmukhi",
  "gurmukhi",
  "roman",
  "latin",
]);

const pieceFields = {
  title: z.string(),
  slug: z.string(),
  language,
  script,
  // Book-sourced pieces have no publication date of their own, only the
  // book's year — a different fact. Nothing in src/ reads this value.
  published: z.coerce.date().optional(),
  tags: z.array(z.string()).default([]),
  published_in: z.array(z.string()).default([]),
  source_book: z.string().optional(),
  book_order: z.number().int().positive().optional(),
};

const piece = (dir: string, extra: Record<string, z.ZodTypeAny> = {}) =>
  defineCollection({
    loader: glob({ pattern: "**/*.md", base: `./content/${dir}` }),
    schema: z.object({ ...pieceFields, ...extra }),
  });

export const collections = {
  ghazals: piece("ghazals", {
    // Date and place of composition, preserved verbatim from the source.
    written_note: z.string().optional(),
    // A tribute set under the poem — (نذرِ غالب), (نذرِ فراقؔ), (نذرِ دردؔ).
    dedication: z.string().optional(),
  }),
  nazms: piece("nazms"),
  memoir: piece("memoir", { part: z.number().int().positive() }),
  reviews: piece("reviews", {
    reviewed_book: z.string().optional(),
    reviewed_author: z.string().optional(),
  }),
  videos: piece("videos", {
    source: z.enum(["youtube", "facebook"]),
    url: z.string().url(),
    video_id: z.string(),
    description: z.string().optional(),
    recorded: z.coerce.date().optional(),
  }),
  containers: defineCollection({
    loader: glob({ pattern: "**/*.yaml", base: "./content/containers" }),
    schema: z.object({
      title: z.string(),
      slug: z.string(),
      description: z.string().optional(),
      // A dead reference here fails the build rather than shipping a dead
      // chapter into the middle of the memoir.
      contents: z.array(reference("memoir")),
    }),
  }),
  books: defineCollection({
    loader: glob({ pattern: "**/*.yaml", base: "./content/books" }),
    schema: z.object({
      title: z.string(),
      slug: z.string(),
      publisher: z.string().optional(),
      // Omitted until the InPage digit codes are mapped; never guessed.
      year: z.number().int().optional(),
      // Which کلیات volume a collection was read from — provenance, not
      // authorship. The collection is the book a reader means.
      collected_in: z.string().optional(),
      contents: z.array(
        z.object({
          section: z.string().optional(),
          kind: z.enum(["ghazals", "nazms"]),
          slug: z.string(),
        }),
      ),
    }),
  }),
};
