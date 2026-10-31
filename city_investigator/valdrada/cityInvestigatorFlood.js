// City Investigator's flood records over Valdrada's ground. Installed into client/src/city/ by
// `python -m city_investigator.valdrada_flood <valdrada folder>` (github.com/yirong-ding/city-investigator).
//
// ?flood=<url> names a JSON with the city flood model's areas around one place, each with the depth of its class,
// and the nearest FloodNet sensor's deepest reading. The areas become Valdrada's own river water standing that depth
// above the street; the reading, a marker pole of its height at the sensor. It shows records, not a simulation of
// water. The model's outlines step along its grid, so they are drawn smoothed (steps under 1.5 m are lost), and the
// water rises out of the street over its last 1.5 m, so it meets the street in a smooth waterline.
//
// Framed by the City Investigator page, it also takes that page's messages once loaded: another place moves the camera
// and swaps the records, so the city is not loaded again (a reload compiles every shader again, minutes on some computers).
import * as THREE from 'three';
import { project } from '../shared/geo.js';

const CELL = 1;        // meters between the water's samples
const HALF = 450;      // meters around the place that are drawn
const ROAD = 0.145;    // the street surface over Valdrada's base ground (main.js RS34)
const SMOOTH = 1.5;    // meters: steps in an outline smaller than this are smoothed away
const RAMP = 1.5;      // meters inside its edge over which the water rises out of the street to its depth
const REACH = 2;       // cells of surface past the water, under the street, so the waterline can fall between samples
const BUCKET = 4;      // meters: the shoreline's segments are looked up by square
const WAIT_S = 120;    // seconds to wait for the ground under the place to stream in

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

function ringsOf(geometry) {
  if (geometry.type === 'Polygon') return geometry.coordinates;
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat();
  return [];
}

function toSegment([px, pz], [ax, az], [bx, bz]) {
  const dx = bx - ax, dz = bz - az, length2 = dx * dx + dz * dz;
  const t = length2 ? clamp(((px - ax) * dx + (pz - az) * dz) / length2, 0, 1) : 0;
  return Math.hypot(px - ax - t * dx, pz - az - t * dz);
}

// Douglas-Peucker: the points that keep a polyline within `tolerance` of itself.
function simplify(points, tolerance) {
  const keep = new Uint8Array(points.length);
  keep[0] = keep[points.length - 1] = 1;
  const spans = [[0, points.length - 1]];
  while (spans.length) {
    const [a, b] = spans.pop();
    let far = -1, most = tolerance;
    for (let i = a + 1; i < b; i++) {
      const d = toSegment(points[i], points[a], points[b]);
      if (d > most) { most = d; far = i; }
    }
    if (far >= 0) { keep[far] = 1; spans.push([a, far], [far, b]); }
  }
  return points.filter((_, i) => keep[i]);
}

// A ring without the steps of the model's grid: simplified, then its corners rounded (Chaikin's corner cutting, each
// cut at most `tolerance` from the corner, so a long straight edge keeps its corners).
export function smoothRing(ring, tolerance = SMOOTH, rounds = 2) {
  const closed = ring.length > 1 && ring[0][0] === ring.at(-1)[0] && ring[0][1] === ring.at(-1)[1];
  let points = closed ? ring.slice(0, -1) : ring.slice();
  if (points.length < 4) return ring;
  let far = 0;   // split at the point farthest from the first: two polylines whose ends stay
  for (let i = 1, most = -1; i < points.length; i++) {
    const d = Math.hypot(points[i][0] - points[0][0], points[i][1] - points[0][1]);
    if (d > most) { most = d; far = i; }
  }
  const halves = [simplify(points.slice(0, far + 1), tolerance), simplify([...points.slice(far), points[0]], tolerance)];
  const simple = [...halves[0].slice(0, -1), ...halves[1].slice(0, -1)];
  if (simple.length >= 3) points = simple;
  for (let round = 0; round < rounds; round++) {
    points = points.flatMap(([ax, az], i) => {
      const [bx, bz] = points[(i + 1) % points.length];
      const cut = Math.min(0.25, tolerance / (Math.hypot(bx - ax, bz - az) || 1));
      return [[ax + cut * (bx - ax), az + cut * (bz - az)], [bx - cut * (bx - ax), bz - cut * (bz - az)]];
    });
  }
  return [...points, points[0]];
}

// The grid cells whose centers lie in an area (even-odd over its rings, so holes stay dry), row by row: cell "i,j" ->
// the deepest class depth that covers it.
export function wetCells(areas, cx, cz, cell = CELL) {
  const depth = new Map();
  const iMin = Math.floor((cx - HALF) / cell), iMax = Math.ceil((cx + HALF) / cell);
  for (const area of areas) {
    const zs = area.rings.flat().map((p) => p[1]);
    const j0 = Math.floor(Math.max(Math.min(...zs), cz - HALF) / cell);
    const j1 = Math.ceil(Math.min(Math.max(...zs), cz + HALF) / cell);
    for (let j = j0; j < j1; j++) {
      const z = (j + 0.5) * cell, xs = [];
      for (const ring of area.rings) {
        for (let a = 0, b = ring.length - 1; a < ring.length; b = a++) {
          const [xa, za] = ring[a], [xb, zb] = ring[b];
          if ((za > z) !== (zb > z)) xs.push(xa + ((z - za) * (xb - xa)) / (zb - za));
        }
      }
      xs.sort((p, q) => p - q);
      for (let k = 0; k + 1 < xs.length; k += 2) {
        const from = Math.max(Math.ceil(xs[k] / cell - 0.5), iMin), to = Math.min(Math.floor(xs[k + 1] / cell - 0.5), iMax);
        for (let i = from; i <= to; i++) {
          const key = `${i},${j}`;
          depth.set(key, Math.max(depth.get(key) ?? 0, area.depth));
        }
      }
    }
  }
  return depth;
}

// The outline's segments between water and dry ground (not those between two depth classes), each with the side the
// water is on: 1 to the left of its direction (x east, z south), -1 to the right.
export function shoreline(areas, depths, cell = CELL) {
  const wet = (x, z) => depths.has(`${Math.floor(x / cell)},${Math.floor(z / cell)}`);
  const segments = [];
  for (const area of areas) {
    for (const ring of area.rings) {
      for (let k = 0; k + 1 < ring.length; k++) {
        const [ax, az] = ring[k], [bx, bz] = ring[k + 1];
        const length = Math.hypot(bx - ax, bz - az);
        if (!length) continue;
        const nx = (-(bz - az) / length) * cell, nz = ((bx - ax) / length) * cell;   // a cell to the left
        const mx = (ax + bx) / 2, mz = (az + bz) / 2;
        const left = wet(mx + nx, mz + nz), right = wet(mx - nx, mz - nz);
        if (left !== right) segments.push({ ax, az, bx, bz, side: left ? 1 : -1 });
      }
    }
  }
  return segments;
}

// Each segment under every square within RAMP of it, so one square holds all the segments that near a point.
function bucketed(segments) {
  const buckets = new Map();
  for (const segment of segments) {
    const { ax, az, bx, bz } = segment;
    for (let j = Math.floor((Math.min(az, bz) - RAMP) / BUCKET); j <= Math.floor((Math.max(az, bz) + RAMP) / BUCKET); j++) {
      for (let i = Math.floor((Math.min(ax, bx) - RAMP) / BUCKET); i <= Math.floor((Math.max(ax, bx) + RAMP) / BUCKET); i++) {
        const key = `${i},${j}`;
        if (!buckets.has(key)) buckets.set(key, []);
        buckets.get(key).push(segment);
      }
    }
  }
  return buckets;
}

// Meters from a point to the shoreline, positive in the water; null when the shoreline is farther than RAMP.
function shoreDistance(x, z, buckets) {
  let best = Infinity, sign = 1, square = 0;
  for (const { ax, az, bx, bz, side } of buckets.get(`${Math.floor(x / BUCKET)},${Math.floor(z / BUCKET)}`) ?? []) {
    const dx = bx - ax, dz = bz - az, length2 = dx * dx + dz * dz;
    const t = clamp(((x - ax) * dx + (z - az) * dz) / length2, 0, 1);
    const d = Math.hypot(x - ax - t * dx, z - az - t * dz);
    const across = (dx * (z - az) - dz * (x - ax)) / Math.sqrt(length2);   // positive to the left
    // at a corner two segments are equally near: the one the point lies squarely across from tells its side
    if (d < best - 1e-9 || (d <= best + 1e-9 && Math.abs(across) > square)) {
      best = d;
      sign = across * side >= 0 ? 1 : -1;
      square = Math.abs(across);
    }
  }
  return best <= RAMP ? best * sign : null;
}

// The water's surface, one shared vertex per grid corner: the class depth over the street, coming up out of the street
// over its last RAMP meters, so the waterline follows the shoreline between the samples instead of their grid.
export function waterSheet(depths, shore, groundAt, cell = CELL) {
  const zone = new Map();   // the wet cells and those within REACH of one: the deepest class near
  for (const [key, depth] of depths) {
    const [i, j] = key.split(',').map(Number);
    for (let dj = -REACH; dj <= REACH; dj++) {
      for (let di = -REACH; di <= REACH; di++) {
        const near = `${i + di},${j + dj}`;
        zone.set(near, Math.max(zone.get(near) ?? 0, depth));
      }
    }
  }
  const buckets = bucketed(shore);
  const positions = [], tops = [], indices = [], index = new Map();
  const vertex = (i, j) => {
    const key = `${i},${j}`;
    let n = index.get(key);
    if (n !== undefined) return n;
    const around = [`${i - 1},${j - 1}`, `${i},${j - 1}`, `${i - 1},${j}`, key];
    const depth = Math.max(...around.map((k) => zone.get(k) ?? 0));
    const x = i * cell, z = j * cell;
    const d = shoreDistance(x, z, buckets) ?? (around.every((k) => depths.has(k)) ? RAMP : -RAMP);
    const top = (depth * d) / RAMP;
    positions.push(x, groundAt(x, z) + ROAD + top, z);
    tops.push(top);
    n = tops.length - 1;
    index.set(key, n);
    return n;
  };
  for (const key of zone.keys()) {
    const [i, j] = key.split(',').map(Number);
    const a = vertex(i, j), b = vertex(i + 1, j), c = vertex(i + 1, j + 1), d = vertex(i, j + 1);
    if (Math.max(tops[a], tops[b], tops[c], tops[d]) <= 0) continue;   // under the street all over
    indices.push(a, d, c, a, c, b);   // counterclockwise seen from above
  }
  return { positions: new Float32Array(positions), indices: new Uint32Array(indices) };
}

// One water material for every overlay, so its shader compiles once.
let water = null;
function waterMaterial() {
  water ??= import('../world/materials.js')
    .then((m) => m.makeWaterMaterial())   // Valdrada's own rivers: ripples, sky, sun
    .catch((e) => {
      console.warn('[city-investigator] Valdrada water material unavailable, plain water instead', e);
      return new THREE.MeshStandardMaterial({ color: 0x3d5650, roughness: 0.08 });
    });
  return water;
}

async function dispose(group) {
  const shared = await water;
  group.traverse((part) => {
    part.geometry?.dispose();
    if (part.material && part.material !== shared) part.material.dispose();
  });
}

export async function addFloodOverlay(scene, streamer, url) {
  const group = await floodOverlay(streamer, url);
  scene.add(group);
  return group;
}

// The records around one place as a group, not yet in the scene.
async function floodOverlay(streamer, url) {
  const data = await (await fetch(url)).json();
  const [cx, cz] = project(data.center.lon, data.center.lat);
  for (let i = 0; i < WAIT_S && streamer.terrainAt(cx, cz) === null; i++) await sleep(1000);
  const base = streamer.terrainAt(cx, cz) ?? 0;
  const groundAt = (x, z) => streamer.terrainAt(x, z) ?? base;
  const areas = data.areas.map((area) => ({
    depth: area.depth_m,
    rings: ringsOf(area.geometry).map((ring) => smoothRing(ring.map(([lon, lat]) => project(lon, lat)))),
  }));
  const group = new THREE.Group();
  group.name = 'city-investigator-flood';
  const depths = wetCells(areas, cx, cz);
  if (depths.size) {
    const { positions, indices } = waterSheet(depths, shoreline(areas, depths), groundAt);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setIndex(new THREE.BufferAttribute(indices, 1));
    geometry.computeBoundingSphere();
    group.add(new THREE.Mesh(geometry, await waterMaterial()));
  }
  if (data.gauge) {
    const [gx, gz] = project(data.gauge.lon, data.gauge.lat);
    const ground = groundAt(gx, gz) + ROAD, height = data.gauge.depth_m;
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, height, 12), new THREE.MeshStandardMaterial({ color: 0xffc400 }));
    pole.position.set(gx, ground + height / 2, gz);
    const mark = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.02, 32), new THREE.MeshStandardMaterial({
      color: 0x0b3d91, transparent: true, opacity: 0.8,
    }));
    mark.position.set(gx, ground + height, gz);
    group.add(pole, mark);
  }
  console.log(`[city-investigator] flood overlay: ${depths.size} m² of water${data.gauge ? ', sensor marker' : ''} (${data.note})`);
  return group;
}

// Called once at boot (the hook in main.js): draws ?flood=<url>, and when Valdrada is framed, takes the framing page's
// {type: 'city-investigator:view', x, z, y, yaw, pitch, rain, flood} to move there, with y over the ground there.
export function connect(scene, streamer, controllerOf, floodUrl) {
  let overlay = null, latest = 0, pending = null;
  const warn = (e) => console.warn('[city-investigator] flood overlay unavailable', e);
  const showFlood = async (url) => {
    const mine = ++latest;
    if (overlay) { scene.remove(overlay); dispose(overlay); overlay = null; }
    if (!url) return;
    const group = await floodOverlay(streamer, url);
    if (mine !== latest) { dispose(group); return; }   // another place was asked for meanwhile
    scene.add(group);
    overlay = group;
  };
  if (floodUrl) showFlood(floodUrl).catch(warn);
  if (window.parent === window) return;
  const move = () => {
    const camera = controllerOf();   // null until Valdrada's boot makes it
    if (!pending || !camera?.pos) return;
    const view = pending;
    pending = null;
    camera.pos.set(view.x, camera.pos.y, view.z);
    camera.relY = view.y;   // the fly camera (?fly=1) stands at this height over the ground once the ground has streamed in
    camera.yaw = view.yaw;
    camera.pitch = view.pitch;
  };
  setInterval(move, 250);
  addEventListener('message', (event) => {
    const view = event.data;
    if (event.source !== window.parent || view?.type !== 'city-investigator:view') return;
    pending = view;
    move();
    if (window.__GFX && typeof view.rain === 'number') window.__GFX.rain = view.rain;   // Valdrada's weather eases to it
    showFlood(view.flood).catch(warn);
  });
  window.parent.postMessage({ type: 'city-investigator:ready' }, '*');
}
