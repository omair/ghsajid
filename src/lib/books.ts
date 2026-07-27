import { getEntry, type CollectionEntry } from "astro:content";

type BookEntry = CollectionEntry<"books">;
type Piece = CollectionEntry<"ghazals"> | CollectionEntry<"nazms">;

export type ResolvedItem = { section: string; entry: Piece };

/**
 * Resolve a book's contents to real entries.
 *
 * `containers` gets dead-reference checking free from `reference()`, which
 * binds a single collection. A book mixes kinds, so the check is explicit:
 * a missing piece throws and fails the build rather than rendering a dead row.
 */
export async function resolveBook(book: BookEntry): Promise<ResolvedItem[]> {
  const items: ResolvedItem[] = [];
  for (const item of book.data.contents) {
    const entry = await getEntry(item.kind, item.slug);
    if (!entry) {
      throw new Error(
        `book ${book.data.slug}: ${item.kind}/${item.slug} does not exist`,
      );
    }
    items.push({ section: item.section ?? "", entry: entry as Piece });
  }
  return items;
}
