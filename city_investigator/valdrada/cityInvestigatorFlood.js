// City Investigator's flood records over Valdrada's ground. Installed into client/src/city/ by
// `python -m city_investigator.valdrada_flood <valdrada folder>` (github.com/yirong-ding/city-investigator).
//
// ?flood=<url> names a JSON with the city flood model's areas around one place, each with the depth of its class,
// and the nearest FloodNet sensor's deepest reading. The areas become Valdrada's own river water standing that depth
// above the street, sinking under the curb at their edges; the reading, a marker pole of its height at the sensor.
// It shows records, not a simulation of water.
//
// Framed by the City Investigator page, it also takes that page's messages once loaded: another place moves the camera
// and swaps the records, so the city is not loaded again (a reload compiles every shader again, minutes on some computers).
import * as THREE from 'three';
import { project } from '../shared/geo.js';

const CELL = 1;        // meters between the water's samples
const HALF = 450;      // meters around the place that are drawn
const ROAD = 0.145;    // the street surface over Valdrada's base ground (main.js RS34)
const SHORE = -0.04;   // the water's edge, just under the street, so it meets the street in a waterline
const WAIT_S = 120;    // seconds to wait for the ground under the place to stream in

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function ringsOf(geometry) {
  if (geometry.type === 'Polygon') return geometry.coordinates;
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat();
  return [];
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

// One shared vertex per grid corner: at the depth above the street where all four cells around it are wet, at the
// waterline where any is dry.
export function waterSheet(depths, groundAt, cell = CELL) {
  const positions = [], indices = [], index = new Map();
  const vertex = (i, j) => {
    const key = `${i},${j}`;
    let n = index.get(key);
    if (n !== undefined) return n;
    const around = [`${i - 1},${j - 1}`, `${i},${j - 1}`, `${i - 1},${j}`, key].map((k) => depths.get(k));
    const top = around.includes(undefined) ? SHORE : Math.max(...around);
    const x = i * cell, z = j * cell;
    positions.push(x, groundAt(x, z) + ROAD + top, z);
    n = positions.length / 3 - 1;
    index.set(key, n);
    return n;
  };
  for (const key of depths.keys()) {
    const [i, j] = key.split(',').map(Number);
    const a = vertex(i, j), b = vertex(i + 1, j), c = vertex(i + 1, j + 1), d = vertex(i, j + 1);
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
    rings: ringsOf(area.geometry).map((ring) => ring.map(([lon, lat]) => project(lon, lat))),
  }));
  const group = new THREE.Group();
  group.name = 'city-investigator-flood';
  const depths = wetCells(areas, cx, cz);
  if (depths.size) {
    const { positions, indices } = waterSheet(depths, groundAt);
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
