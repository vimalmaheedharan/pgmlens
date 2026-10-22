// Layered left-to-right layout: blockers sit left of the work they block.

export interface LayoutEdge {
  source: string;
  target: string;
}

export interface Placement {
  x: number;
  y: number;
  layer: number;
}

export function layerLayout(
  ids: string[],
  edges: LayoutEdge[],
  { colWidth = 270, rowHeight = 96 }: { colWidth?: number; rowHeight?: number } = {},
): Map<string, Placement> {
  const known = new Set(ids);
  const valid = edges.filter((e) => known.has(e.source) && known.has(e.target) && e.source !== e.target);
  const preds = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of valid) preds.get(e.target)!.push(e.source);

  // Layer = longest chain of blockers above a node. Iterating |V| times also tames cycles.
  const layer = new Map<string, number>(ids.map((id) => [id, 0]));
  for (let pass = 0; pass < ids.length; pass++) {
    let changed = false;
    for (const e of valid) {
      const next = (layer.get(e.source) ?? 0) + 1;
      if (next > (layer.get(e.target) ?? 0) && next < ids.length) {
        layer.set(e.target, next);
        changed = true;
      }
    }
    if (!changed) break;
  }

  const columns = new Map<number, string[]>();
  for (const id of [...ids].sort()) {
    const l = layer.get(id) ?? 0;
    columns.set(l, [...(columns.get(l) ?? []), id]);
  }

  // One barycenter sweep left to right keeps connected nodes near each other.
  const row = new Map<string, number>();
  const placed = new Map<string, Placement>();
  for (const l of [...columns.keys()].sort((a, b) => a - b)) {
    const members = columns.get(l)!;
    const score = (id: string) => {
      const above = (preds.get(id) ?? []).filter((p) => row.has(p));
      return above.length ? above.reduce((sum, p) => sum + row.get(p)!, 0) / above.length : Number.MAX_SAFE_INTEGER;
    };
    members.sort((a, b) => score(a) - score(b) || a.localeCompare(b));
    members.forEach((id, index) => {
      row.set(id, index);
      placed.set(id, { x: l * colWidth, y: index * rowHeight, layer: l });
    });
  }
  return placed;
}
