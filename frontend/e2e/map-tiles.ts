import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { BrowserContext } from '@playwright/test';

// Automated UI tests use a local fixture; never bulk-request public OSM tiles.
export const mapTile=readFileSync(path.resolve('e2e/fixtures/map-tile.png'));
export async function mockMapTiles(context:BrowserContext) {
  await context.route('https://tile.openstreetmap.org/**',route=>route.fulfill({contentType:'image/png',body:mapTile}));
}
