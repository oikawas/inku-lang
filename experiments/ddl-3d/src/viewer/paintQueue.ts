/** Front layers first; marks sharing a layer keep their order. */
export function paintOrder<T>(items: readonly T[], layerZ: (item: T) => number): T[] {
  return [...items].sort((a, b) => layerZ(b) - layerZ(a));
}

/** Start each item in the given order, at most `limit` at a time. A failure
 * leaves the others running and comes back with its item. */
export async function paintInTurn<T>(items: readonly T[], limit: number, paint: (item: T) => Promise<void>,
  stopped: () => boolean = () => false): Promise<{ item: T; error: unknown }[]> {
  const failures: { item: T; error: unknown }[] = [];
  let next = 0;
  const lane = async () => {
    while (next < items.length && !stopped()) {
      const item = items[next++];
      try { await paint(item); } catch (error) { failures.push({ item, error }); }
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, lane));
  return failures;
}
