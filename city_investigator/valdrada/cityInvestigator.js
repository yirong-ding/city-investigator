// City Investigator's records over Valdrada's city. Installed into client/src/city/ by
// `python -m city_investigator.valdrada_addon <valdrada folder>` (github.com/yirong-ding/city-investigator).
//
// ?scene=<url> names a run's scene (city_investigator/scene3d.py), drawn in place, each piece labeled with the record
// or photo it comes from:
// - the flood: the city flood model's areas as Valdrada's own river water standing their class depth above the street,
//   and the nearest FloodNet sensor's deepest reading as a marker pole of that height. The model's outlines step along
//   its grid, so they are drawn smoothed (steps under 1.5 m are lost), and the water rises out of the street over its
//   last 1.5 m, so it meets the street in a smooth waterline;
// - sheds: buildings with a shed or scaffold permit valid on the photo's date, with Valdrada's own shed model along
//   each wall that faces a sidewalk, as deep as the sidewalk;
// - seen: scaffolding found in the photo, the same shed along the building front it was traced to from the camera;
// - facades: buildings whose latest façade filing is UNSAFE, their street walls washed red;
// - after: the explanation's proposals, shown when the page switches to After: each action done as an illustration
//   (curbside rain gardens on the sidewalks around the low spot, the shed an unsafe façade must have, a young tree),
//   or a label where the action has no picture. Not a design and not a prediction: the flood water stays as recorded.
// Valdrada places sidewalk sheds at random (about 1 in 80 building fronts); they are taken away here, so every shed in
// view is a record or the photo. It shows records, not a simulation.
//
// Framed by the City Investigator page, it also takes that page's messages once loaded: another place moves the camera
// and swaps the scene, so the city is not loaded again (a reload compiles every shader again, minutes on some computers).
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
const WALK = new Set(['sidewalk', 'path', 'brick', 'plaza', 'gravel']);   // Valdrada's walking surfaces (assemble.js)
const CURB_M = 8;      // a sidewalk is measured out to this width at most
const SHED_DEPTH = 4.4;   // Valdrada's default shed depth, where the sidewalk cannot be measured
const WALL_MIN = 2;    // meters: shorter walls get no shed
const COLORS = { record: '#f2a900', photo: '#3d8bfd', unsafe: '#d92b2b', proposal: '#2b7a3d' };
const GARDEN = [6, 1.5];   // meters along and across the curb: a curbside rain garden's size
const GARDENS = 3;     // rain gardens shown around a low spot
const LABEL_Y = 5.6;   // meters over the sidewalk: a label clears a shed's parapet

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

// Only what this module made is disposed: Valdrada's shed models share their geometry and materials.
function own(object) {
  object.userData.cityInvestigator = true;
  return object;
}

async function dispose(group) {
  const shared = await water;
  group.traverse((part) => {
    if (!part.userData.cityInvestigator) return;
    part.geometry?.dispose();
    if (part.material && part.material !== shared) {
      part.material.map?.dispose();
      part.material.dispose();
    }
  });
}

// Valdrada's tile under a point has streamed in (roadAt answers null only where it has not).
const loaded = (streamer, [x, z]) => streamer.roadAt(x, z) !== null;

async function until(test, seconds = WAIT_S) {
  for (let i = 0; i < seconds * 4 && !test(); i++) await sleep(250);
  return test();
}

// Valdrada's street pieces (city/pk/props.js), with their materials loaded.
let pieces = null;
function streetPieces() {
  pieces ??= import('./pk/props.js').then(async (m) => { await m.ready; return m; });
  return pieces;
}

// The flood records: Valdrada's river water over the model's areas, and the sensor's marker pole.
async function floodParts(flood, groundAt, cx, cz) {
  const group = new THREE.Group();
  const areas = flood.areas.map((area) => ({
    depth: area.depth_m,
    rings: ringsOf(area.geometry).map((ring) => smoothRing(ring.map(([lon, lat]) => project(lon, lat)))),
  }));
  const depths = wetCells(areas, cx, cz);
  if (depths.size) {
    const { positions, indices } = waterSheet(depths, shoreline(areas, depths), groundAt);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setIndex(new THREE.BufferAttribute(indices, 1));
    geometry.computeBoundingSphere();
    group.add(own(new THREE.Mesh(geometry, await waterMaterial())));
  }
  if (flood.gauge) {
    const [gx, gz] = project(flood.gauge.lon, flood.gauge.lat);
    const ground = groundAt(gx, gz) + ROAD, height = flood.gauge.depth_m;
    const pole = own(new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, height, 12), new THREE.MeshStandardMaterial({ color: 0xffc400 })));
    pole.position.set(gx, ground + height / 2, gz);
    const mark = own(new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.02, 32), new THREE.MeshStandardMaterial({
      color: 0x0b3d91, transparent: true, opacity: 0.8,
    })));
    mark.position.set(gx, ground + height, gz);
    group.add(pole, mark);
  }
  console.log(`[city-investigator] flood: ${depths.size} m² of water${flood.gauge ? ', sensor marker' : ''}`);
  return group;
}

function inside([x, z], ring) {
  let hit = false;
  for (let a = 0, b = ring.length - 1; a < ring.length; b = a++) {
    const [xa, za] = ring[a], [xb, zb] = ring[b];
    if ((za > z) !== (zb > z) && x < xa + ((z - za) * (xb - xa)) / (zb - za)) hit = !hit;
  }
  return hit;
}

// A wall from a to b, with n the unit normal on the side away from the building (toward the street).
function wall(a, b, outward) {
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
  let n = [-(b[1] - a[1]) / length, (b[0] - a[0]) / length];
  if (!outward(n, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2])) n = [-n[0], -n[1]];
  return { a, b, n, length, mid: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] };
}

// How far the sidewalk in front of a wall reaches before the roadway; null when there is no sidewalk there.
function sidewalkDepth(streamer, w) {
  const at = (s) => streamer.surfaceInfoAt(w.mid[0] + w.n[0] * s, w.mid[1] + w.n[1] * s);
  if (!WALK.has(at(1)?.kind)) return null;
  for (let s = 1.25; s <= CURB_M; s += 0.25) if (at(s)?.road) return s;
  return SHED_DEPTH;
}

// The walls of a footprint that face a sidewalk.
function streetWalls(streamer, rings) {
  const walls = [];
  for (const ring of rings) {
    const away = (n, mid) => !inside([mid[0] + n[0] * 0.3, mid[1] + n[1] * 0.3], ring);
    for (let k = 0; k + 1 < ring.length; k++) {
      const w = wall(ring[k], ring[k + 1], away);
      if (w.length < WALL_MIN) continue;
      w.depth = sidewalkDepth(streamer, w);
      if (w.depth !== null) walls.push(w);
    }
  }
  return walls;
}

function surfaceY(streamer, x, z) {
  const info = streamer.surfaceInfoAt(x, z);
  return info && Number.isFinite(info.y) ? info.y : (streamer.terrainAt(x, z) ?? 0) + 0.28;
}

// Text in lines of at most `width` characters, at most `most` lines, the last cut short with an ellipsis.
function wrap(text, width = 44, most = 3) {
  const lines = [];
  for (const word of String(text || '').split(/\s+/).filter(Boolean)) {
    const last = lines.length - 1;
    if (last >= 0 && (lines[last] + ' ' + word).length <= width) lines[last] += ' ' + word;
    else lines.push(word);
  }
  if (lines.length <= most) return lines;
  const kept = lines.slice(0, most);
  kept[most - 1] = kept[most - 1].slice(0, width - 1) + '…';
  return kept;
}

// A label over a piece: what it is, in its color, then where it comes from (wrapped).
function label(lines, color, x, y, z) {
  const rest = wrap(lines.slice(1).join(' '));
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 108 + 64 * rest.length;
  const g = canvas.getContext('2d');
  g.fillStyle = 'rgba(16, 20, 24, 0.82)';
  g.fillRect(0, 0, canvas.width, canvas.height);
  g.fillStyle = color;
  g.fillRect(0, 0, 18, canvas.height);
  g.font = 'bold 58px Arial, Helvetica, sans-serif';
  g.fillText(lines[0], 44, 78);
  g.fillStyle = '#ffffff';
  g.font = '44px Arial, Helvetica, sans-serif';
  rest.forEach((line, i) => g.fillText(line, 44, 150 + 64 * i));
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = own(new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, toneMapped: false })));
  sprite.scale.set(6.4, (6.4 * canvas.height) / canvas.width, 1);
  sprite.position.set(x, y + sprite.scale.y / 2 - 0.6, z);
  return sprite;
}

// Valdrada's shed along a wall, as deep as the sidewalk, over a strip of the source's color.
function shedAlong(props, streamer, w, color) {
  const group = new THREE.Group();
  const depth = clamp(Math.round(((w.depth ?? SHED_DEPTH) - 0.3) * 2) / 2, 2, 6);
  const length = Math.max(3, Math.round(w.length * 2) / 2);
  const [cx, cz] = [w.mid[0] + w.n[0] * (depth / 2 + 0.15), w.mid[1] + w.n[1] * (depth / 2 + 0.15)];
  const y = surfaceY(streamer, cx, cz);
  const shed = props.modelGroup('shed', { len: length, dep: depth }, 1);
  shed.position.set(cx, y, cz);
  shed.rotation.y = Math.atan2(w.n[0], w.n[1]);   // the model's +z, its roadway side, along the wall's outward normal
  const strip = own(new THREE.Mesh(new THREE.PlaneGeometry(length, depth), new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0.4, depthWrite: false, toneMapped: false,
  })));
  strip.rotation.set(-Math.PI / 2, Math.atan2(w.n[0], w.n[1]), 0, 'YXZ');   // laid flat, then turned along the wall
  strip.position.set(cx, y + 0.03, cz);
  group.add(shed, strip);
  return { group };
}

// A building's street walls washed red, the full height of the building.
function facadeWash(streamer, walls, height, color) {
  const group = new THREE.Group();
  for (const w of walls) {
    const y = surfaceY(streamer, w.mid[0] + w.n[0], w.mid[1] + w.n[1]);
    const plane = own(new THREE.Mesh(new THREE.PlaneGeometry(w.length, height), new THREE.MeshBasicMaterial({
      color, transparent: true, opacity: 0.32, side: THREE.DoubleSide, depthWrite: false, toneMapped: false,
    })));
    plane.position.set(w.mid[0] + w.n[0] * 0.15, y + height / 2, w.mid[1] + w.n[1] * 0.15);
    plane.rotation.y = Math.atan2(w.n[0], w.n[1]);
    group.add(plane);
  }
  return group;
}

// A curbside rain garden: a low stone rim round a planted bed, its long side along the curb (local x), the curb at +z.
function rainGarden() {
  const group = new THREE.Group();
  const [length, width] = GARDEN;
  const stone = new THREE.MeshStandardMaterial({ color: 0xb9b4a8, roughness: 0.9 });
  for (const [w, d, x, z] of [[length, 0.15, 0, (width - 0.15) / 2], [length, 0.15, 0, -(width - 0.15) / 2],
    [0.15, width, (length - 0.15) / 2, 0], [0.15, width, -(length - 0.15) / 2, 0]]) {
    const rim = own(new THREE.Mesh(new THREE.BoxGeometry(w, 0.16, d), stone));
    rim.position.set(x, 0.08, z);
    group.add(rim);
  }
  const bed = own(new THREE.Mesh(new THREE.PlaneGeometry(length - 0.3, width - 0.3), new THREE.MeshStandardMaterial({ color: 0x3b2f22, roughness: 1 })));
  bed.rotation.x = -Math.PI / 2;
  bed.position.y = 0.03;
  group.add(bed);
  const greens = [0x4f7a32, 0x5d8a3a, 0x3f6b2a, 0x6b8f3e].map((color) => new THREE.MeshStandardMaterial({ color, roughness: 0.85 }));
  for (let i = 0; i < 16; i++) {   // grasses and shrubs, spread along the bed
    const r = 0.18 + 0.12 * Math.abs(Math.sin(i * 7.31));
    const plant = own(new THREE.Mesh(new THREE.IcosahedronGeometry(r, 0), greens[i % greens.length]));
    plant.scale.y = 1.4;
    plant.position.set(((i + 0.5) / 16 - 0.5) * (length - 0.6), r * 1.1, Math.sin(i * 3.7) * (width / 2 - 0.4));
    group.add(plant);
  }
  return group;
}

// A young street tree in its pit.
function youngTree() {
  const group = new THREE.Group();
  const pit = own(new THREE.Mesh(new THREE.PlaneGeometry(1.2, 1.2), new THREE.MeshStandardMaterial({ color: 0x3b2f22, roughness: 1 })));
  pit.rotation.x = -Math.PI / 2;
  pit.position.y = 0.03;
  const trunk = own(new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.06, 2.6, 8), new THREE.MeshStandardMaterial({ color: 0x5a4632, roughness: 0.9 })));
  trunk.position.y = 1.3;
  const crown = own(new THREE.Mesh(new THREE.IcosahedronGeometry(0.85, 1), new THREE.MeshStandardMaterial({ color: 0x5d8a3a, roughness: 0.8 })));
  crown.scale.y = 1.25;
  crown.position.y = 2.9;
  group.add(pit, trunk, crown);
  return group;
}

// The nearest roadway from a sidewalk point within 3 m: its direction and distance.
function curbFrom(streamer, x, z) {
  let best = null;
  for (let k = 0; k < 16; k++) {
    const d = [Math.sin((k * Math.PI) / 8), Math.cos((k * Math.PI) / 8)];
    for (let s = 0.25; s <= 3 && (!best || s < best.s); s += 0.25) {
      if (streamer.surfaceInfoAt(x + d[0] * s, z + d[1] * s)?.road) { best = { d, s }; break; }
    }
  }
  return best;
}

// Where rain gardens could go around a low spot: sidewalk along a curb, on ground higher than the spot (water runs
// down to it) where there is any, nearer first, at least 15 m apart; each set back 0.3 m from the curb.
function gardenSpots(streamer, cx, cz) {
  const base = streamer.terrainAt(cx, cz) ?? 0;
  const candidates = [];
  for (const r of [10, 16, 22, 28, 34, 40]) {
    for (let a = 0; a < 360; a += 10) {
      const x = cx + r * Math.sin((a * Math.PI) / 180), z = cz + r * Math.cos((a * Math.PI) / 180);
      const curb = WALK.has(streamer.surfaceInfoAt(x, z)?.kind) ? curbFrom(streamer, x, z) : null;
      if (!curb) continue;
      const shift = curb.s - 0.3 - GARDEN[1] / 2;
      const [gx, gz] = [x + curb.d[0] * shift, z + curb.d[1] * shift];
      const along = [curb.d[1], -curb.d[0]];
      const corners = [[1, 1], [1, -1], [-1, 1], [-1, -1]].map(([u, v]) => [
        gx + along[0] * u * GARDEN[0] / 2 + curb.d[0] * v * GARDEN[1] / 2, gz + along[1] * u * GARDEN[0] / 2 + curb.d[1] * v * GARDEN[1] / 2]);
      if (!corners.every(([qx, qz]) => WALK.has(streamer.surfaceInfoAt(qx, qz)?.kind))) continue;
      candidates.push({ x: gx, z: gz, r, higher: (streamer.terrainAt(gx, gz) ?? base) > base + 0.05, d: curb.d });
    }
  }
  candidates.sort((p, q) => q.higher - p.higher || p.r - q.r);
  const spots = [];
  for (const c of candidates) if (spots.length < GARDENS && spots.every((s) => Math.hypot(s.x - c.x, s.z - c.z) > 15)) spots.push(c);
  return spots;
}

// The proposals, drawn as illustrations of each action done, each with a label of the proposal.
async function afterGroup(streamer, items, props) {
  const group = new THREE.Group();
  group.name = 'city-investigator-after';
  const stacked = new Map();   // labels at one place stack upward
  const note = (item, x, y, z) => {
    const key = `${Math.round(x)},${Math.round(z)}`;
    const n = stacked.get(key) ?? 0;
    stacked.set(key, n + 1);
    group.add(label(['Proposal (illustration)', item.text], COLORS.proposal, x, y + 2.4 * n, z));
  };
  for (const item of items) {
    const [x, z] = project(...item.at);
    await until(() => loaded(streamer, [x, z]), 30);
    if (item.draw === 'rain_gardens') {
      const spots = gardenSpots(streamer, x, z);
      for (const spot of spots) {
        const garden = rainGarden();
        garden.position.set(spot.x, surfaceY(streamer, spot.x, spot.z), spot.z);
        garden.rotation.y = Math.atan2(spot.d[0], spot.d[1]);
        group.add(garden);
      }
      const first = spots[0] ?? { x, z };
      note(item, first.x, surfaceY(streamer, first.x, first.z) + 2.2, first.z);
      if (!spots.length) console.warn('[city-investigator] no sidewalk along a curb near the low spot for rain gardens');
    } else if (item.draw === 'shed' && item.rings && props) {
      const walls = streetWalls(streamer, item.rings.map((ring) => ring.map(([lon, lat]) => project(lon, lat))));
      for (const w of walls) group.add(shedAlong(props, streamer, w, COLORS.proposal).group);
      const front = walls.sort((p, q) => q.length - p.length)[0];
      const [lx, lz] = front ? [front.mid[0] + front.n[0] * 2, front.mid[1] + front.n[1] * 2] : [x, z];
      note(item, lx, surfaceY(streamer, lx, lz) + LABEL_Y + 3.2, lz);
    } else if (item.draw === 'young_tree') {
      const tree = youngTree();
      tree.position.set(x, surfaceY(streamer, x, z), z);
      group.add(tree);
      note(item, x, surfaceY(streamer, x, z) + 4.6, z);
    } else {
      note(item, x, surfaceY(streamer, x, z) + LABEL_Y, z);
    }
  }
  console.log(`[city-investigator] after: ${items.length} proposal(s): ${items.map((item) => item.draw || 'label').join(', ')}`);
  return group;
}

// The run's scene around one place, as a group not yet in the city.
async function sceneGroup(streamer, url) {
  const data = await (await fetch(url)).json();
  const [cx, cz] = project(data.center.lon, data.center.lat);
  await until(() => streamer.terrainAt(cx, cz) !== null && loaded(streamer, [cx, cz]));
  const base = streamer.terrainAt(cx, cz) ?? 0;
  const groundAt = (x, z) => streamer.terrainAt(x, z) ?? base;
  const group = new THREE.Group();
  group.name = 'city-investigator';
  if (data.flood) group.add(await floodParts(data.flood, groundAt, cx, cz));
  const ringsOfItem = (item) => item.rings.map((ring) => ring.map(([lon, lat]) => project(lon, lat)));
  const props = (data.sheds?.length || data.seen?.length || data.after?.some((item) => item.draw === 'shed')) ? await streetPieces() : null;
  const permitted = [];   // the walls with a permitted shed drawn
  for (const item of data.sheds || []) {
    const rings = ringsOfItem(item);
    await until(() => loaded(streamer, rings[0][0]), 30);
    const walls = streetWalls(streamer, rings);
    if (!walls.length) console.warn(`[city-investigator] ${item.label}, ${item.address || 'a building'}: no wall faces a sidewalk here`);
    for (const w of walls) group.add(shedAlong(props, streamer, w, COLORS.record).group);
    permitted.push(...walls);
    const front = walls.sort((p, q) => q.length - p.length)[0];
    if (front) {
      const [x, z] = [front.mid[0] + front.n[0] * 2, front.mid[1] + front.n[1] * 2];
      group.add(label([item.label, item.address], COLORS.record, x, surfaceY(streamer, x, z) + LABEL_Y, z));
    }
  }
  for (const item of data.seen || []) {
    const a = project(...item.a), b = project(...item.b), camera = project(...item.camera);
    await until(() => loaded(streamer, a), 30);
    const toward = (n, mid) => (camera[0] - mid[0]) * n[0] + (camera[1] - mid[1]) * n[1] > 0;
    const w = wall(a, b, toward);
    w.depth = sidewalkDepth(streamer, w) ?? SHED_DEPTH;
    const note = [item.label, `SAM 3.1, ${item.distance_m} m from the camera`];
    // where the photo's scaffolding stands in front of a permitted shed, the photo adds its label, not a second shed
    const covered = permitted.some((r) => toSegment(w.mid, r.a, r.b) < 1 && r.n[0] * w.n[0] + r.n[1] * w.n[1] > 0.9);
    const [x, z] = [w.mid[0] + w.n[0] * 2, w.mid[1] + w.n[1] * 2];
    if (!covered) group.add(shedAlong(props, streamer, w, COLORS.photo).group);
    group.add(label(note, COLORS.photo, x, surfaceY(streamer, x, z) + LABEL_Y + (covered ? 1.6 : 0), z));
  }
  for (const item of data.facades || []) {
    const rings = ringsOfItem(item);
    await until(() => loaded(streamer, rings[0][0]), 30);
    const walls = streetWalls(streamer, rings);
    if (!walls.length) console.warn(`[city-investigator] ${item.label}, ${item.address || 'a building'}: no wall faces a sidewalk here`);
    const height = item.height_m || 12;
    group.add(facadeWash(streamer, walls, height, COLORS.unsafe));
    const front = walls.sort((p, q) => q.length - p.length)[0];
    if (front) {
      const [x, z] = [front.mid[0] + front.n[0] * 1.5, front.mid[1] + front.n[1] * 1.5];
      group.add(label([item.label, item.address], COLORS.unsafe, x, surfaceY(streamer, x, z) + Math.min(height, 14) + 1, z));
    }
  }
  console.log(`[city-investigator] scene: ${data.sheds?.length || 0} permitted sheds, ${data.seen?.length || 0} seen in the photo, ${data.facades?.length || 0} unsafe façades${data.flood ? ', flood' : ''}`);
  group.add(await afterGroup(streamer, data.after || [], props));
  return group;
}

// Valdrada's randomly placed sheds (the instancer's 'scaffold' pool) are released, including those of tiles that
// stream in later, so a shed in view always comes from a record or the photo.
function clearRandomSheds(instancer) {
  const pool = instancer?.pools?.get('scaffold');
  if (!pool?.alive) return 0;
  let cleared = 0;
  for (let i = 0; i < pool.top; i++) if (pool.alive[i]) { instancer.release('scaffold', i); cleared++; }
  return cleared;
}

// Called once at boot (the hook in main.js): draws ?scene=<url>, and when Valdrada is framed, takes the framing page's
// {type: 'city-investigator:view', x, z, y, yaw, pitch, rain, scene} to move there, with y over the ground there, and
// {type: 'city-investigator:after', on} to show the proposals or not (not by default; also when Valdrada is not framed).
export function connect({ scene, streamer, instancer, camera: controllerOf }, sceneUrl) {
  let shown = null, latest = 0, pending = null, after = new URLSearchParams(location.search).get('after') === '1';
  const showAfter = () => { const part = shown?.getObjectByName?.('city-investigator-after'); if (part) part.visible = after; };
  const warn = (e) => console.warn('[city-investigator] scene unavailable', e);
  const showScene = async (url) => {
    const mine = ++latest;
    if (shown) { scene.remove(shown); dispose(shown); shown = null; }
    if (!url) return;
    const group = await sceneGroup(streamer, url);
    if (mine !== latest) { dispose(group); return; }   // another place was asked for meanwhile
    scene.add(group);
    shown = group;
    showAfter();
  };
  clearRandomSheds(instancer);
  streamer.onTile?.(() => clearRandomSheds(instancer), () => {});
  setInterval(() => clearRandomSheds(instancer), 2000);
  if (sceneUrl) showScene(sceneUrl).catch(warn);
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
    if (event.source === window.parent && view?.type === 'city-investigator:after') { after = !!view.on; showAfter(); return; }
    if (event.source !== window.parent || view?.type !== 'city-investigator:view') return;
    pending = view;
    move();
    if (window.__GFX && typeof view.rain === 'number') window.__GFX.rain = view.rain;   // Valdrada's weather eases to it
    showScene(view.scene).catch(warn);
  });
  window.parent.postMessage({ type: 'city-investigator:ready' }, '*');
}
