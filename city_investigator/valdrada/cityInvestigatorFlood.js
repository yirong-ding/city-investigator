// City Investigator's flood records over Valdrada's ground. Installed into client/src/city/ by
// `python -m city_investigator.valdrada_flood <valdrada folder>` (github.com/yirong-ding/city-investigator).
//
// ?flood=<url> names a JSON with the city flood model's areas around one place, each with the depth of its class,
// and the nearest FloodNet sensor's deepest reading. The areas become a sheet of water that depth above the street,
// the reading a marker pole of its height at the sensor. It shows records, not a simulation of water.
import * as THREE from 'three';
import { project } from '../shared/geo.js';

const CELL = 3;        // meters between the water sheet's samples
const HALF = 450;      // meters around the place that are drawn
const ROAD = 0.145;    // the street surface over Valdrada's base ground (main.js RS34)
const WAIT_S = 120;    // seconds to wait for the ground under the place to stream in

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function ringsOf(geometry) {
  if (geometry.type === 'Polygon') return geometry.coordinates;
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat();
  return [];
}

// Even-odd rule over every ring, so holes in an area stay dry.
export function inside(x, z, rings) {
  let hit = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, zi] = ring[i], [xj, zj] = ring[j];
      if ((zi > z) !== (zj > z) && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) hit = !hit;
    }
  }
  return hit;
}

// Two triangles per grid cell whose center lies in an area, each corner at its depth above the street there.
export function waterSheet(areas, groundAt, cx, cz) {
  const positions = [];
  for (const area of areas) {
    const xs = area.rings.flat().map((p) => p[0]), zs = area.rings.flat().map((p) => p[1]);
    const x0 = Math.max(Math.min(...xs), cx - HALF), x1 = Math.min(Math.max(...xs), cx + HALF);
    const z0 = Math.max(Math.min(...zs), cz - HALF), z1 = Math.min(Math.max(...zs), cz + HALF);
    const top = (x, z) => groundAt(x, z) + ROAD + area.depth;
    for (let x = Math.floor(x0 / CELL) * CELL; x < x1; x += CELL) {
      for (let z = Math.floor(z0 / CELL) * CELL; z < z1; z += CELL) {
        if (!inside(x + CELL / 2, z + CELL / 2, area.rings)) continue;
        const a = [x, top(x, z), z], b = [x + CELL, top(x + CELL, z), z];
        const c = [x + CELL, top(x + CELL, z + CELL), z + CELL], d = [x, top(x, z + CELL), z + CELL];
        positions.push(...a, ...d, ...c, ...a, ...c, ...b);
      }
    }
  }
  return new Float32Array(positions);
}

export async function addFloodOverlay(scene, streamer, url) {
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
  const sheet = waterSheet(areas, groundAt, cx, cz);
  if (sheet.length) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(sheet, 3));
    geometry.computeVertexNormals();
    const water = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
      color: 0x2f6db5, transparent: true, opacity: 0.62, roughness: 0.08, metalness: 0.0,
      depthWrite: false, side: THREE.DoubleSide,
    }));
    water.renderOrder = 2;
    group.add(water);
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
  scene.add(group);
  console.log(`[city-investigator] flood overlay: ${sheet.length / 18} cells${data.gauge ? ', sensor marker' : ''} (${data.note})`);
  return group;
}
