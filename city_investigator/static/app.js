'use strict';

// City Investigator page: photo -> confirmed pin -> question -> live progress -> answer, map, timeline.

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron';
const DISTRICT = [-73.995, 40.675];
const KINDS = { observation: 'Observed', record: 'Record', model: 'Model', hypothesis: 'Inferred', no_coverage: 'No coverage' };
const GROUPS = {
  complaint: { name: '311 complaint', color: '#d9480f', row: 'Complaints' },
  permit: { name: 'Permit or license', color: '#5f3dc4', row: 'Permits and licenses' },
  agency: { name: 'Agency inspection, order or filing', color: '#1971c2', row: 'Agency actions' },
  inventory: { name: 'City inventory (tree, ramp)', color: '#2b8a3e' },
  sensor: { name: 'FloodNet flood', color: '#0b7285', row: 'Sensor floods' },
  rain: { name: 'Rain', color: '#4a6fa5', row: 'Rain' },
  lot: { name: 'Property lot', color: '#868e96' },
  other: { name: 'Other record', color: '#495057' },
};
const ROWS = ['Complaints', 'Permits and licenses', 'Agency actions', 'Sensor floods', 'Rain'];
const FLOOD = { 1: '#74a9e8', 2: '#1c4fb8', 3: '#0c8599' };
const SCENARIOS = { moderate_current: "Today's sea levels", moderate_2050: '2050 sea levels' };
// How a batch site's flags compare the records with the street, worst first.
const WORST = {
  conflict: { color: '#c92a2a', name: 'Records and street disagree' },
  gap: { color: '#e8890c', name: 'A gap in the records' },
  agreement: { color: '#2b8a3e', name: 'Records and street agree' },
  none: { color: '#868e96', name: 'No flags' },
};

// Valdrada, the 3D city of NYC (github.com/mkturkcan/valdrada), running on this computer: its dev server's address
// and the projection of its world (client/src/shared/geo.js), x east and z south in meters. Its online demo is a
// light edition holding only a few Manhattan places, so it cannot show the district.
const VALDRADA = 'http://127.0.0.1:5219';
const VALDRADA_ORIGIN = { lat: 40.7831, lon: -73.9712 };
// Depth classes of the city's flood model, drawn in 3D at a height inside each class.
const FLOOD_HEIGHT_M = { 1: 0.2, 2: 0.45, 3: 0.3 };
const EXTRUSIONS = ['buildings3d', 'flood3d', 'gauge3d'];

const state = {
  view3d: false, mode: 'run',
  map: null, marker: null, photo: null, pin: null, run: null, confirming: false,
  scenario: 'moderate_current', source: null, nextEvent: 0, started: 0, timer: null, highlighted: [],
};

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'text') node.textContent = value;
    else if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined));
  return node;
}

function svg(tag, attrs = {}) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = '';
    try { detail = (await response.json()).detail; } catch { /* not JSON */ }
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

const empty = () => ({ type: 'FeatureCollection', features: [] });

// Map

async function baseStyle() {
  // The page still works offline: without tiles the map is a plain background under the records.
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 4000);
    const response = await fetch(BASEMAP, { signal: controller.signal });
    clearTimeout(timer);
    if (response.ok) return await response.json();
  } catch { /* fall through */ }
  return { version: 8, sources: {}, layers: [{ id: 'paper', type: 'background', paint: { 'background-color': '#eceae4' } }] };
}

async function initMap() {
  if (!window.maplibregl) {
    $('map').append(el('p', { class: 'map-missing', text: 'The map could not load (offline?). Everything else still works.' }));
    return;
  }
  const map = new maplibregl.Map({ container: 'map', style: await baseStyle(), center: DISTRICT, zoom: 13.4, attributionControl: { compact: true } });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  await new Promise((resolve) => map.on('load', resolve));
  const lit = ['boolean', ['feature-state', 'hl'], false];
  map.addSource('flood', { type: 'geojson', data: empty() });
  map.addLayer({
    id: 'flood', type: 'fill', source: 'flood',
    filter: ['==', ['get', 'scenario'], state.scenario],
    paint: { 'fill-color': ['match', ['get', 'category'], 1, FLOOD[1], 2, FLOOD[2], 3, FLOOD[3], '#888'], 'fill-opacity': 0.4 },
  });
  map.addSource('rings', { type: 'geojson', data: empty() });
  map.addLayer({ id: 'uncertainty', type: 'fill', source: 'rings', filter: ['==', ['get', 'kind'], 'uncertainty'], paint: { 'fill-color': '#0f5c63', 'fill-opacity': 0.12 } });
  map.addLayer({ id: 'radius', type: 'line', source: 'rings', filter: ['==', ['get', 'kind'], 'radius'], paint: { 'line-color': '#0f5c63', 'line-width': 1.5, 'line-dasharray': [3, 2] } });
  map.addSource('records', { type: 'geojson', data: empty(), promoteId: 'id' });
  map.addLayer({
    id: 'records', type: 'circle', source: 'records',
    paint: {
      'circle-radius': ['case', lit, 9, 6],
      'circle-color': ['match', ['get', 'group'], ...Object.entries(GROUPS).flatMap(([key, value]) => [key, value.color]), '#495057'],
      'circle-stroke-color': ['case', lit, '#111111', '#ffffff'],
      'circle-stroke-width': ['case', lit, 2.5, 1.5],
    },
  });
  map.addSource('sites', { type: 'geojson', data: empty() });
  map.addLayer({
    id: 'sites', type: 'circle', source: 'sites',
    paint: {
      'circle-radius': 8,
      'circle-color': ['match', ['get', 'worst'], ...Object.entries(WORST).flatMap(([key, value]) => [key, value.color]), '#868e96'],
      'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2,
    },
  });
  // 3D: the city's footprints at their roof heights, the flood model's water at its depth class and the
  // sensor's deepest flood as a column; around the district overview, the basemap's buildings.
  map.addSource('buildings', { type: 'geojson', data: empty() });
  map.addSource('gauge', { type: 'geojson', data: empty() });
  const hidden = { visibility: 'none' };
  if (map.getSource('openmaptiles')) {
    map.addLayer({
      id: 'osm3d', type: 'fill-extrusion', source: 'openmaptiles', 'source-layer': 'building', layout: hidden,
      paint: {
        'fill-extrusion-color': '#d7d5cf', 'fill-extrusion-opacity': 0.85,
        'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 8],
        'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
      },
    }, 'records');
  }
  map.addLayer({
    id: 'buildings3d', type: 'fill-extrusion', source: 'buildings', layout: hidden,
    paint: {
      'fill-extrusion-color': ['case', ['get', 'cited'], '#d9480f', ['get', 'measured'], '#cfccc4', '#e6e3dc'],
      'fill-extrusion-height': ['get', 'height'], 'fill-extrusion-opacity': 0.9,
    },
  }, 'records');
  map.addLayer({
    id: 'flood3d', type: 'fill-extrusion', source: 'flood', layout: hidden,
    filter: ['==', ['get', 'scenario'], state.scenario],
    paint: {
      'fill-extrusion-color': ['match', ['get', 'category'], 1, FLOOD[1], 2, FLOOD[2], 3, FLOOD[3], '#888'],
      'fill-extrusion-height': ['match', ['get', 'category'], ...Object.entries(FLOOD_HEIGHT_M).flatMap(([k, v]) => [Number(k), v]), 0.3],
      'fill-extrusion-opacity': 0.6,
    },
  }, 'records');
  map.addLayer({
    id: 'gauge3d', type: 'fill-extrusion', source: 'gauge', layout: hidden,
    paint: { 'fill-extrusion-color': '#0b3d91', 'fill-extrusion-height': ['get', 'height'], 'fill-extrusion-opacity': 0.95 },
  }, 'records');
  map.addControl({
    onAdd() {
      const box = el('div', { class: 'maplibregl-ctrl maplibregl-ctrl-group' });
      box.append(el('button', { type: 'button', id: 'toggle-3d', class: 'view-toggle', text: '3D', title: 'Tilt the map and raise the buildings', onclick: () => { state.view3d = !state.view3d; apply3d(true); } }));
      return box;
    },
    onRemove() {},
  }, 'top-right');
  map.on('click', 'sites', (event) => sitePopup(event.features[0]));
  map.on('mouseenter', 'sites', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'sites', () => { map.getCanvas().style.cursor = ''; });
  map.on('click', 'records', (event) => openPopup(event.features[0].properties));
  map.on('mouseenter', 'records', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'records', () => { map.getCanvas().style.cursor = ''; });
  map.on('click', (event) => {
    if (!state.confirming || map.queryRenderedFeatures(event.point, { layers: ['records'] }).length) return;
    setPin(event.lngLat.lat, event.lngLat.lng, true);
  });
  state.map = map;
}

function circle(lat, lon, meters, kind) {
  const points = [];
  const dLat = meters / 110574;
  const dLon = meters / (111320 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= 64; i += 1) {
    const angle = (i / 64) * 2 * Math.PI;
    points.push([lon + dLon * Math.cos(angle), lat + dLat * Math.sin(angle)]);
  }
  return { type: 'Feature', properties: { kind }, geometry: { type: 'Polygon', coordinates: [points] } };
}

function setPin(lat, lon, draggable, uncertainty = null, radius = null) {
  state.pin = { lat, lon };
  showPinReadout();
  if (!state.map) return;
  if (!state.marker) {
    state.marker = new maplibregl.Marker({ element: el('div', { class: 'pin', title: 'Where the photo was taken' }) })
      .setLngLat([lon, lat]).addTo(state.map);
    state.marker.on('dragend', () => {
      const point = state.marker.getLngLat();
      state.pin = { lat: point.lat, lon: point.lng };
      showPinReadout(true);
    });
  }
  state.marker.setLngLat([lon, lat]).setDraggable(draggable);
  state.marker.getElement().classList.toggle('draggable', draggable);
  const rings = [];
  if (uncertainty) rings.push(circle(lat, lon, uncertainty, 'uncertainty'));
  if (radius) rings.push(circle(lat, lon, radius, 'radius'));
  state.map.getSource('rings').setData({ type: 'FeatureCollection', features: rings });
}

function showPinReadout(moved = false) {
  if (!state.pin) return;
  const source = moved ? 'moved by you' : `from ${state.photo?.location_source || 'the photo'}`;
  $('pin-readout').textContent = `Pin: ${state.pin.lat.toFixed(6)}, ${state.pin.lon.toFixed(6)} (${source})`;
}

function openPopup(properties) {
  if (!state.map) return;
  const feature = state.map.querySourceFeatures('records').find((item) => item.properties.id === properties.id);
  const coordinates = feature ? feature.geometry.coordinates : null;
  if (!coordinates) return;
  const citing = (state.run?.explanation?.claims || []).filter((claim) => claim.evidence_ids.includes(properties.id)).length;
  const body = el('div', {},
    el('strong', { text: GROUPS[properties.group]?.name || 'Record' }),
    el('p', { text: properties.summary }),
    properties.address ? el('p', { class: 'meta', text: properties.address }) : null,
    citing ? el('p', { class: 'meta', text: `Cited by ${citing} claim${citing > 1 ? 's' : ''}` }) : null,
    properties.url ? el('a', { href: properties.url, target: '_blank', rel: 'noopener', text: 'Open the record' }) : null);
  new maplibregl.Popup({ offset: 10 }).setLngLat(coordinates).setDOMContent(body).addTo(state.map);
}

function renderLegend(data) {
  const legend = $('legend');
  legend.replaceChildren();
  const counts = {};
  for (const feature of data.map.records.features) counts[feature.properties.group] = (counts[feature.properties.group] || 0) + 1;
  for (const [group, count] of Object.entries(counts)) {
    const spec = GROUPS[group] || GROUPS.other;
    legend.append(el('div', { class: 'item' }, el('span', { class: 'swatch', style: `background:${spec.color}` }), `${spec.name} (${count})`));
  }
  const flood = data.map.flood.features;
  if (flood.length) {
    legend.append(el('h4', { text: "City flood model, moderate storm (2.13 in/hr)" }));
    const seen = new Map(flood.map((feature) => [feature.properties.category, feature.properties.label]));
    for (const [category, label] of [...seen].sort()) {
      legend.append(el('div', { class: 'item' }, el('span', { class: 'swatch area', style: `background:${FLOOD[category]}` }), label));
    }
    const scenarios = [...new Set(flood.map((feature) => feature.properties.scenario))];
    if (scenarios.length > 1) {
      const toggle = el('div', { class: 'toggle' });
      for (const scenario of scenarios) {
        toggle.append(el('button', {
          type: 'button', class: scenario === state.scenario ? 'on' : '', text: SCENARIOS[scenario] || scenario,
          onclick: () => {
            state.scenario = scenario;
            for (const layer of ['flood', 'flood3d']) state.map?.setFilter(layer, ['==', ['get', 'scenario'], scenario]);
            renderLegend(data);
          },
        }));
      }
      legend.append(toggle);
    }
  }
  const buildings = data.map.buildings?.features || [];
  if (buildings.length) {
    legend.append(el('h4', { text: 'In 3D' }),
      el('div', { class: 'item' }, el('span', { class: 'swatch area', style: 'background:#cfccc4' }), 'Buildings at their measured roof heights (city footprints)'));
    if (buildings.some((feature) => feature.properties.cited)) {
      legend.append(el('div', { class: 'item' }, el('span', { class: 'swatch area', style: 'background:#d9480f' }), 'A building the flags or the answer cite'));
    }
  }
  for (const column of data.map.gauge?.features || []) {
    legend.append(el('div', { class: 'item' }, el('span', { class: 'swatch area', style: 'background:#0b3d91' }), `Column: ${column.properties.label}`));
  }
  legend.append(el('div', { class: 'item meta' }, el('span', { class: 'swatch', style: 'background:#0f5c63' }), `Photo pin; dashed ring: ${data.map.pin.radius_m} m searched`));
  legend.hidden = false;
}

function renderMap(data) {
  renderLegend(data);
  const { pin } = data.map;
  if (!state.map) return;
  state.map.getSource('records').setData(data.map.records);
  state.map.getSource('flood').setData(data.map.flood);
  state.map.getSource('buildings').setData(data.map.buildings || empty());
  state.map.getSource('gauge').setData(data.map.gauge || empty());
  for (const layer of ['flood', 'flood3d']) state.map.setFilter(layer, ['==', ['get', 'scenario'], state.scenario]);
  setPin(pin.lat, pin.lon, false, pin.uncertainty_m, pin.radius_m);
  const ring = circle(pin.lat, pin.lon, pin.radius_m * 1.25, 'fit').geometry.coordinates[0];
  const bounds = ring.reduce((box, point) => box.extend(point), new maplibregl.LngLatBounds(ring[0], ring[0]));
  state.map.fitBounds(bounds, { padding: 30, maxZoom: 18.5, duration: 700, ...view3dCamera(data.map.heading_deg) });
  apply3d(false);
}

// 3D: which extrusions show in each mode, and the camera tilt. Looking along the photo's compass heading puts the
// buildings the camera saw in front of the viewer.

function view3dCamera(heading) {
  return state.view3d ? { pitch: 60, bearing: typeof heading === 'number' ? heading : -20 } : { pitch: 0, bearing: 0 };
}

function apply3d(move) {
  const map = state.map;
  if (!map) return;
  const show = (layer, on) => map.getLayer(layer) && map.setLayoutProperty(layer, 'visibility', on ? 'visible' : 'none');
  for (const layer of EXTRUSIONS) show(layer, state.view3d && state.mode === 'run');
  show('osm3d', state.view3d && state.mode === 'overview');
  show('flood', !state.view3d);
  $('toggle-3d')?.classList.toggle('on', state.view3d);
  $('toggle-3d') && ($('toggle-3d').textContent = state.view3d ? '2D' : '3D');
  if (move) map.easeTo({ ...view3dCamera(state.mode === 'run' ? state.run?.map?.heading_deg : null), duration: 800 });
}

// Valdrada: the same spot in the 3D city, standing at eye height and facing the photo's direction.

function valdradaLink(map, base) {
  const { lat, lon } = map.pin;
  const metersPerDegLon = 111320 * Math.cos((VALDRADA_ORIGIN.lat * Math.PI) / 180);
  const x = (lon - VALDRADA_ORIGIN.lon) * metersPerDegLon;
  const z = -(lat - VALDRADA_ORIGIN.lat) * 111132;
  const yaw = typeof map.heading_deg === 'number' ? (-map.heading_deg * Math.PI) / 180 : 0;  // yaw 0 looks north, turning left
  // Light settings, for a look at one place: Valdrada's low tier (600 m of full detail), far view to 5 km instead of 13,
  // no traffic or pedestrians (their models are the heaviest download), and a 5 s wait for the landmarks module.
  // fly=1: Valdrada's fly camera, the one that reads y relative to its own ground (rel=1); its default drone takes y
  // as height above sea level, so 1.7 m can sit at or under the street where the ground is a few meters up.
  const query = new URLSearchParams({
    x: x.toFixed(1), z: z.toFixed(1), y: '1.7', rel: '1', fly: '1', yaw: yaw.toFixed(3), pitch: '0', hud: '0',
    tier: 'low', macro: '5000', nosim: '1', lmwait: '5',
  });
  if (state.run?.result?.topic === 'flooding') query.set('rain', '1');
  return `${base}/?${query}`;
}

// Highlighting: a claim or flag lights up the evidence it cites, on the map and the timeline.

function highlight(ids) {
  const map = state.map;
  if (map) {
    for (const id of state.highlighted) map.setFeatureState({ source: 'records', id }, { hl: false });
    const known = new Set((state.run?.map.records.features || []).map((feature) => feature.properties.id));
    for (const id of ids) if (known.has(id)) map.setFeatureState({ source: 'records', id }, { hl: true });
    map.setPaintProperty('flood', 'fill-opacity', ids.some((id) => id.startsWith('stormwater:')) ? 0.7 : 0.4);
  }
  state.highlighted = ids;
  state.marker?.getElement().classList.toggle('hl', ids.some((id) => id === 'photo' || id.startsWith('photo:')));
  const timeline = $('timeline');
  let lit = 0;
  for (const mark of timeline.querySelectorAll('.mark')) {
    const on = ids.includes(mark.dataset.id);
    mark.classList.toggle('hl', on);
    lit += on ? 1 : 0;
  }
  timeline.classList.toggle('dim', lit > 0);
}

function hoverable(node, ids) {
  node.addEventListener('mouseenter', () => highlight(ids));
  node.addEventListener('mouseleave', () => highlight([]));
  node.addEventListener('focusin', () => highlight(ids));
  node.addEventListener('focusout', () => highlight([]));
}

function focusEvidence(id) {
  const feature = state.run?.map.records.features.find((item) => item.properties.id === id);
  if (feature && state.map) {
    state.map.flyTo({ center: feature.geometry.coordinates, zoom: Math.max(state.map.getZoom(), 17) });
    openPopup(feature.properties);
    return;
  }
  selectTab('sources');
  const row = document.querySelector(`[data-source="${CSS.escape(id)}"]`);
  if (row) {
    row.scrollIntoView({ block: 'center', behavior: 'smooth' });
    row.classList.add('flash');
    setTimeout(() => row.classList.remove('flash'), 1600);
  }
}

// Evidence helpers

function allEvidence(data) {
  const items = new Map();
  for (const record of data.result.records) {
    items.set(record.id, { id: record.id, group: record.group, summary: record.summary, address: record.address, distance_m: record.distance_m, url: record.url, date: record.start?.local, until: record.end?.local });
  }
  for (const [id, item] of Object.entries(data.explanation?.evidence || {})) {
    if (!items.has(id)) items.set(id, { ...item, id });
  }
  return items;
}

function shortName(id, item) {
  if (id === 'photo') return 'photo';
  const [prefix, rest] = id.split(/:(.*)/s);
  const names = {
    photo: `photo: ${rest.replace('not_seen:', 'no ').replaceAll('_', ' ')}`,
    '311': `311 #${rest}`,
    floodnet: `sensor ${item?.date ? item.date.slice(5) : 'event'}`,
    stormwater: 'city flood model',
    recurrence: `history: ${rest.replaceAll('_', ' ')}`,
    coverage: `coverage: ${rest.split('@')[0].replaceAll('_', ' ')}`,
    flag: `flag: ${rest.replaceAll('_', ' ')}`,
    rain: 'rain',
    shed_history: 'shed history',
    pluto: 'property lot',
    dobnow: 'DOB permit',
    doblegacy: 'DOB permit',
    tree_points: 'tree (Parks inventory)',
    tree_inspections: 'tree inspection',
    tree_work_orders: 'tree work order',
    facade_filings: 'façade filing',
    sidewalk_violations: 'sidewalk violation',
    tree_sidewalk_damage: 'tree damage record',
    ramps: 'ramp survey',
    ramp_complaints: 'ramp complaint',
    pothole_orders: 'pothole work order',
    street_permits: 'street permit',
    street_closures: 'street closure',
    dining_licenses: 'dining license',
    dining_inspections: 'dining inspection',
  };
  return names[prefix] || id;
}

function rowOf(item) {
  return GROUPS[item.group]?.row || null;
}

// Panels

function selectTab(name) {
  for (const button of document.querySelectorAll('.tabs button')) button.classList.toggle('active', button.dataset.tab === name);
  for (const tab of document.querySelectorAll('.tab')) tab.hidden = tab.id !== `tab-${name}`;
}

function renderAnswer(data, waiting) {
  const tab = $('tab-answer');
  const { result, explanation } = data;
  tab.replaceChildren(
    el('h3', { class: 'question', text: result.question }),
    el('p', { class: 'meta', text: `About ${result.question_moment} New York time · ${result.topic_label || result.topic} · records within ${result.radius_m} m of the pin` }));
  if (!explanation) {
    tab.append(el('p', { class: 'waiting', text: waiting ? 'Muse Spark is reading the evidence and writing the answer…' : 'This run has no explanation yet.' }));
    return;
  }
  const evidence = allEvidence(data);
  const list = el('ol', { class: 'claims' });
  for (const claim of explanation.claims) {
    const cites = el('div', { class: 'cites' });
    for (const id of claim.evidence_ids) {
      cites.append(el('button', { type: 'button', class: 'chip', title: evidence.get(id)?.summary || id, text: shortName(id, evidence.get(id)), onclick: () => focusEvidence(id) }));
    }
    const item = el('li', { class: `claim kind-${claim.kind}`, tabindex: '0' },
      el('span', { class: 'kind', text: KINDS[claim.kind] || claim.kind }), el('p', { text: claim.text }), cites);
    hoverable(item, claim.evidence_ids);
    list.append(item);
  }
  tab.append(list);
  if (explanation.models_disagree?.length) {
    tab.append(el('div', { class: 'box warn' }, el('strong', { text: 'Muse Spark and SAM 3.1 disagree' }),
      ...explanation.models_disagree.map((note) => el('p', { text: note }))));
  }
  if (explanation.tool_calls?.length) {
    tab.append(el('details', {}, el('summary', { text: `What Muse Spark checked (${explanation.tool_calls.length})` }),
      el('ul', {}, ...explanation.tool_calls.map((call) => {
        const args = typeof call.arguments === 'object' ? Object.entries(call.arguments).map(([key, value]) => `${key}=${value}`).join(', ') : call.arguments;
        return el('li', { text: `${call.tool}(${args}): ${call.outcome}` });
      }))));
  }
  const removed = [...explanation.dropped.map((item) => `Removed: ${item.claim?.text || JSON.stringify(item.claim)} (${item.problems.join('; ')})`), ...explanation.warnings];
  if (removed.length) {
    tab.append(el('details', {}, el('summary', { text: `Caught by the evidence checks (${removed.length})` }), el('ul', {}, ...removed.map((text) => el('li', { text })))));
  }
  const total = explanation.claims.length + explanation.dropped.length;
  tab.append(el('p', {
    class: 'checks',
    text: `Written by Muse Spark (${explanation.model}) in ${explanation.seconds} s. Checks: ${explanation.claims.length} of ${total} claims passed, `
      + `${explanation.repairs} repair round(s), ${explanation.tool_calls.length} lookup(s)`
      + (explanation.estimated_cost_usd !== undefined ? `, about $${explanation.estimated_cost_usd.toFixed(3)}.` : '.'),
  }));
}

function renderFlags(data) {
  const tab = $('tab-flags');
  const flags = data.result.flags;
  tab.replaceChildren(el('p', { class: 'hint', text: 'Flags come from fixed rules that compare the photo and the records, not from the model.' }));
  if (!flags.length) { tab.append(el('p', { text: 'No flags raised.' })); return; }
  const list = el('ul', { class: 'flags' });
  for (const flag of flags) {
    const item = el('li', { class: `flag sev-${flag.severity}`, tabindex: '0' }, el('span', { class: 'kind', text: flag.severity }), flag.message);
    hoverable(item, flag.evidence_ids);
    list.append(item);
  }
  tab.append(list);
}

function renderPhoto(data) {
  const tab = $('tab-photo');
  const { result, name } = data;
  const image = el('img', { src: `/api/runs/${encodeURIComponent(name)}/files/overlay.png`, alt: 'The photo with what SAM 3.1 found outlined' });
  const toggle = el('div', { class: 'toggle' });
  const choose = (file, button) => {
    image.src = `/api/runs/${encodeURIComponent(name)}/files/${file}`;
    for (const other of toggle.children) other.classList.toggle('on', other === button);
  };
  const outlined = el('button', { type: 'button', class: 'on', text: 'What SAM 3.1 found' });
  const plain = el('button', { type: 'button', text: 'Photo only' });
  outlined.addEventListener('click', () => choose('overlay.png', outlined));
  plain.addEventListener('click', () => choose('photo.jpg', plain));
  toggle.append(outlined, plain);
  const photo = result.photo;
  tab.replaceChildren(el('div', { class: 'photo-tab' }, image), toggle,
    el('p', {}, el('strong', { text: 'Seen: ' }), result.observations.map((item) => item.summary.replace('The photo shows ', '')).join('; ') || 'nothing the question is about'),
    result.not_seen.length ? el('p', {}, el('strong', { text: 'Not found: ' }), result.not_seen.join(', ')) : null,
    el('p', { class: 'meta', text: `Taken ${photo.taken_local} New York time. Faces and license plates ${photo.faces_and_plates}.` }),
    photo.credit ? el('p', { class: 'meta' }, photo.page_url ? el('a', { href: photo.page_url, target: '_blank', rel: 'noopener', text: photo.credit }) : photo.credit) : null,
    el('p', { class: 'meta' },
      el('a', { href: valdradaLink(data.map, VALDRADA), target: '_blank', rel: 'noopener', text: 'See this spot in Valdrada' }),
      ', the 3D city of New York, when it runs on this computer. Its streets are built from public records, but some '
      + 'details such as sidewalk sheds are placed at random, so it shows the place, not the evidence.'));
}

function renderSources(data) {
  const tab = $('tab-sources');
  const list = el('ul', { class: 'sources' });
  for (const item of allEvidence(data).values()) {
    if (item.type === 'flag') continue;
    const place = [item.address, item.distance_m !== undefined && item.distance_m !== null ? `${item.distance_m} m away` : null].filter(Boolean).join(', ');
    list.append(el('li', { 'data-source': item.id },
      el('code', { text: item.id }), el('br'),
      place ? el('span', { class: 'meta', text: `${place} · ` }) : null,
      item.summary, ' ',
      item.url ? el('a', { href: item.url, target: '_blank', rel: 'noopener', text: 'source' }) : null));
  }
  const coverage = el('ul', { class: 'sources' });
  for (const note of data.result.coverage) {
    coverage.append(el('li', {}, el('span', { class: `state state-${note.state}`, text: note.state.replace('_', ' ') }), el('strong', { text: `${note.source}: ` }), note.note));
  }
  tab.replaceChildren(el('h3', { class: 'meta', text: 'Records, models and the photo' }), list,
    el('h3', { class: 'meta', text: 'What each source can and cannot see' }), coverage);
}

// Timeline

function parseLocal(text) {
  if (!text) return null;
  const date = new Date(text.length <= 10 ? `${text}T12:00` : text.replace(' ', 'T'));
  return Number.isNaN(date.getTime()) ? null : date;
}

function timelineItems(data) {
  const items = [];
  for (const item of allEvidence(data).values()) {
    const row = rowOf(item);
    const start = parseLocal(item.date);
    if (!row || !start) continue;
    items.push({ id: item.id, row, start, end: parseLocal(item.until), summary: item.summary });
  }
  return items;
}

function ticks(t0, t1) {
  const span = t1 - t0;
  const day = 864e5;
  const out = [];
  if (span > 3 * 365 * day) {
    for (let year = new Date(t0).getFullYear() + 1; year <= new Date(t1).getFullYear(); year += 1) out.push([new Date(year, 0, 1), String(year)]);
  } else if (span > 60 * day) {
    const step = span > 365 * day ? 3 : 1;
    const date = new Date(new Date(t0).getFullYear(), new Date(t0).getMonth() + 1, 1);
    while (date <= t1) {
      out.push([new Date(date), date.toLocaleDateString('en-US', { month: 'short', year: date.getMonth() === 0 || out.length === 0 ? 'numeric' : undefined })]);
      date.setMonth(date.getMonth() + step);
    }
  } else {
    const step = span > 10 * day ? 7 : 1;
    const date = new Date(new Date(t0).setHours(0, 0, 0, 0) + day);
    while (date <= t1) {
      out.push([new Date(date), date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })]);
      date.setDate(date.getDate() + step);
    }
  }
  return out;
}

function renderTimeline(data) {
  const host = $('timeline');
  host.replaceChildren();
  const items = timelineItems(data);
  const photoTime = parseLocal(data.result.photo.taken_local);
  const asked = parseLocal(data.result.question_moment);
  if (!items.length) { host.append(el('p', { class: 'meta', text: 'No dated records near this pin.' })); return; }
  const rows = ROWS.filter((row) => items.some((item) => item.row === row));
  const recordTimes = items.flatMap((item) => [item.start, item.end || item.start]).map(Number);
  let t0 = Math.min(...recordTimes, asked ? Number(asked) : Infinity);
  let t1 = Math.max(...recordTimes, asked ? Number(asked) : -Infinity);
  // A photo from long before or after the records would squash them; note it instead of plotting it.
  const month = 30 * 864e5;
  const photoOnAxis = photoTime && photoTime >= t0 - month && photoTime <= t1 + month;
  if (photoOnAxis) { t0 = Math.min(t0, Number(photoTime)); t1 = Math.max(t1, Number(photoTime)); }
  const pad = Math.max((t1 - t0) * 0.04, 864e5);
  t0 -= pad; t1 += pad;
  const width = Math.max(host.clientWidth, 320);
  const left = 92;
  const rowHeight = 30;
  const top = 18;
  const height = top + rows.length * rowHeight + 20;
  const x = (time) => left + ((time - t0) / (t1 - t0)) * (width - left - 12);
  const chart = svg('svg', { width, height, role: 'img', 'aria-label': 'Timeline of the records' });
  for (const [time, label] of ticks(t0, t1)) {
    chart.append(svg('line', { class: 'grid', x1: x(time), x2: x(time), y1: top - 4, y2: height - 18 }));
    const text = svg('text', { class: 'axis', x: x(time), y: height - 4, 'text-anchor': 'middle' });
    text.textContent = label;
    chart.append(text);
  }
  rows.forEach((row, index) => {
    const text = svg('text', { class: 'row-label', x: 0, y: top + index * rowHeight + rowHeight / 2 + 4 });
    text.textContent = row;
    chart.append(text);
  });
  const colors = Object.fromEntries(Object.values(GROUPS).filter((g) => g.row).map((g) => [g.row, g.color]));
  for (const item of items) {
    const y = top + rows.indexOf(item.row) * rowHeight + rowHeight / 2;
    const mark = item.end && item.end > item.start
      ? svg('rect', { x: x(item.start), y: y - 5, width: Math.max(x(item.end) - x(item.start), 3), height: 10, rx: 3 })
      : svg('circle', { cx: x(item.start), cy: y, r: 5 });
    mark.setAttribute('class', 'mark');
    mark.setAttribute('fill', colors[item.row]);
    mark.setAttribute('fill-opacity', item.end ? 0.55 : 0.9);
    mark.dataset.id = item.id;
    const title = svg('title');
    title.textContent = item.summary;
    mark.append(title);
    mark.addEventListener('click', () => focusEvidence(item.id));
    chart.append(mark);
  }
  const moments = [[photoOnAxis ? photoTime : null, 'Photo', ''], [asked, 'Asked about', ' asked']];
  if (photoOnAxis && asked && Math.abs(photoTime - asked) < 36e5) moments.pop();
  for (const [time, label, extra] of moments) {
    if (!time) continue;
    chart.append(svg('line', { class: `moment${extra}`, x1: x(time), x2: x(time), y1: top - 6, y2: height - 18 }));
    const text = svg('text', { class: 'moment-label', x: x(time) + 4, y: top - 8 });
    text.textContent = label;
    chart.append(text);
  }
  host.append(chart);
  if (photoTime && !photoOnAxis) {
    host.append(el('p', { class: 'meta', text: `The photo was taken ${data.result.photo.taken_local}, outside this window.` }));
  }
}

// Running an investigation

function addStep(message, kind = '') {
  const list = $('progress');
  for (const item of list.children) item.classList.remove('active');
  const seconds = Math.round((Date.now() - state.started) / 1000);
  list.append(el('li', { class: kind || 'active' }, el('span', { text: message }), el('span', { class: 'when', text: `${seconds}s` })));
}

function stopProgress(ok) {
  clearInterval(state.timer);
  for (const item of $('progress').children) item.classList.remove('active');
  $('investigate').disabled = false;
  state.source?.close();
  state.source = null;
  if (ok) addStep('Done', 'done');
}

function handleEvent(event) {
  if (event.n < state.nextEvent) return; // already shown before a reconnect
  state.nextEvent = event.n + 1;
  if (event.type === 'progress') addStep(event.message);
  else if (event.type === 'investigated') loadRun(event.run, { waiting: true });
  else if (event.type === 'done') {
    stopProgress(true);
    refreshRuns(event.run);
    loadRun(event.run).then(() => $('results').scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }
  else if (event.type === 'error') { stopProgress(false); addStep(event.message, 'error'); }
}

async function investigate() {
  const question = $('question').value.trim();
  if (!state.photo || !state.pin) { setStatus('Load a photo first.', true); return; }
  if (!question) { $('question').focus(); return; }
  const taken = $('taken').value;
  const body = {
    photo: state.photo.photo, lat: state.pin.lat, lon: state.pin.lon, question,
    taken: taken ? taken.replace('T', ' ') : null, when: $('when').value || null,
    topic: $('topic').value || null, provider: $('provider').value, explain: true,
  };
  $('investigate').disabled = true;
  $('progress').replaceChildren();
  $('progress-card').hidden = false;
  $('results').hidden = true;
  $('photo-preview').classList.add('compact');
  $('progress-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
  state.started = Date.now();
  state.nextEvent = 0;
  clearInterval(state.timer);
  state.timer = setInterval(() => { $('elapsed').textContent = `${Math.round((Date.now() - state.started) / 1000)}s`; }, 1000);
  try {
    const { job } = await api('/api/investigations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    state.source = new EventSource(`/api/jobs/${job}/events`);
    state.source.onmessage = (message) => handleEvent(JSON.parse(message.data));
  } catch (error) {
    stopProgress(false);
    addStep(error.message, 'error');
  }
}

// The district overview: every place of the last batch run, colored by its worst flag.

const words = (text) => String(text).replaceAll('_', ' ');

function sitePopup(feature) {
  const site = typeof feature.properties.flags === 'string'
    ? { ...feature.properties, flags: JSON.parse(feature.properties.flags) } : feature.properties;
  const worst = WORST[site.worst] || WORST.none;
  const body = el('div', { class: 'site-popup' },
    el('strong', { text: `${site.label}: ${site.place}` }),
    el('p', {}, el('span', { class: 'swatch', style: `background:${worst.color};display:inline-block;margin-right:6px` }), worst.name),
    site.flags.length ? el('p', { class: 'meta', text: site.flags.map(words).join(', ') }) : null,
    site.answer ? el('p', { text: site.answer }) : null,
    el('button', { type: 'button', class: 'primary', text: 'Open the investigation', onclick: () => { popup.remove(); loadRun(site.run); } }));
  const popup = new maplibregl.Popup({ offset: 10, maxWidth: '320px' }).setLngLat(feature.geometry.coordinates).setDOMContent(body).addTo(state.map);
}

function overviewLegend(sites) {
  const legend = $('legend');
  const counts = {};
  for (const site of sites.features) counts[site.properties.worst] = (counts[site.properties.worst] || 0) + 1;
  legend.replaceChildren(el('h4', { text: 'Places investigated' }),
    ...Object.entries(WORST).filter(([key]) => counts[key]).map(([key, value]) =>
      el('div', { class: 'item' }, el('span', { class: 'swatch', style: `background:${value.color}` }), `${value.name} (${counts[key]})`)));
  legend.hidden = false;
}

async function showOverview() {
  const { summary, sites } = await api('/api/batch');
  const stat = (value, label) => el('div', { class: 'stat' }, el('strong', { text: String(value) }), el('span', { text: label }));
  const share = summary.claims_kept_share === null ? '-' : `${Math.round(summary.claims_kept_share * 100)}%`;
  $('overview-stats').replaceChildren(
    stat(summary.sites, 'places investigated'),
    stat(summary.sites_records_and_photo_disagree ?? '-', 'where the records and the photo disagree'),
    stat(share, `of ${summary.claims_kept + summary.claims_removed} claims kept after checking`),
    stat(summary.lookups.check_photo || 0, 'times Muse Spark asked SAM 3.1 to look again'));
  const order = Object.keys(WORST);
  const ranked = [...sites.features].sort((a, b) => order.indexOf(a.properties.worst) - order.indexOf(b.properties.worst));
  $('overview-list').replaceChildren(...ranked.map((feature) => {
    const site = feature.properties;
    return el('li', {}, el('button', { type: 'button', class: 'secondary', onclick: () => {
      state.map?.flyTo({ center: feature.geometry.coordinates, zoom: 16 });
      if (state.map) sitePopup(feature);
    } }, el('span', { class: 'swatch', style: `background:${(WORST[site.worst] || WORST.none).color}` }),
    el('span', {}, el('strong', { text: site.place }), ` · ${site.label}`, site.flags.length ? el('br') : null,
      site.flags.length ? el('span', { class: 'meta', text: site.flags.map(words).join(', ') }) : null)));
  }));
  $('overview-card').hidden = false;
  $('results').hidden = true;
  overviewLegend(sites);
  history.replaceState(null, '', '#overview');
  state.mode = 'overview';
  showStage('map');
  $('show-valdrada').disabled = true;
  apply3d(false);
  if (!state.map) return;
  for (const source of ['records', 'flood', 'rings']) state.map.getSource(source).setData(empty());
  state.marker?.remove();
  state.marker = null;
  state.map.getSource('sites').setData(sites);
  if (sites.features.length) {
    const points = sites.features.map((feature) => feature.geometry.coordinates);
    const bounds = points.reduce((box, point) => box.extend(point), new maplibregl.LngLatBounds(points[0], points[0]));
    state.map.fitBounds(bounds, { padding: 50, maxZoom: 15, duration: 700, ...view3dCamera(null) });
  }
}

// The stage shows the map or, for an open investigation, the same spot in Valdrada running on this computer.

function showStage(view) {
  if (view === 'valdrada' && !state.run) return;
  document.querySelector('.stage').dataset.view = view;
  for (const button of document.querySelectorAll('.stage-switch button')) button.classList.toggle('on', button.dataset.view === view);
  if (view === 'valdrada') {
    const link = valdradaLink(state.run.map, VALDRADA);
    if ($('valdrada-frame').getAttribute('src') !== link) $('valdrada-frame').setAttribute('src', link);  // loads only when shown
    $('valdrada-tab').href = link;
  } else {
    state.map?.resize();
  }
}

async function loadRun(name, { waiting = false } = {}) {
  const data = await api(`/api/runs/${encodeURIComponent(name)}`);
  state.run = data;
  state.confirming = false;
  $('overview-card').hidden = true;
  state.map?.getSource('sites').setData(empty());
  state.mode = 'run';
  $('show-valdrada').disabled = false;
  $('show-valdrada').title = 'This spot in Valdrada, a 3D city of New York';
  renderMap(data);
  renderTimeline(data);
  renderAnswer(data, waiting);
  renderFlags(data);
  renderPhoto(data);
  renderSources(data);
  $('results').hidden = false;
  history.replaceState(null, '', `#run=${encodeURIComponent(name)}`);
  if (document.querySelector('.stage').dataset.view === 'valdrada') showStage('valdrada');  // follow the new spot
}

// Bringing in a photo

function setStatus(text, isError = false) {
  const status = $('photo-status');
  status.hidden = !text;
  status.textContent = text || '';
  status.classList.toggle('error', isError);
}

async function loadPhoto(form) {
  setStatus('Loading the photo…');
  try {
    const photo = await api('/api/photos', { method: 'POST', body: form });
    state.photo = photo;
    setStatus('');
    $('preview-img').src = photo.preview;
    $('photo-preview').classList.remove('compact');
    const where = photo.lat === null ? 'no location in the photo: click the map to place the pin'
      : `location from ${photo.location_source}, about ${Math.round(photo.uncertainty_m)} m`;
    $('photo-meta').replaceChildren(`${photo.taken_local ? `Taken ${photo.taken_local}` : 'No date in the photo'} · ${where}`,
      photo.credit ? el('br') : null, photo.credit || null);
    $('photo-preview').hidden = false;
    $('step-place').hidden = false;
    $('step-question').hidden = false;
    $('taken').value = photo.taken_local ? photo.taken_local.replace(' ', 'T') : '';
    state.confirming = true;
    state.run = null;
    $('results').hidden = true;
    $('progress-card').hidden = true;
    if (photo.lat !== null) {
      setPin(photo.lat, photo.lon, true, photo.uncertainty_m);
      state.map?.flyTo({ center: [photo.lon, photo.lat], zoom: 18 });
    } else {
      state.pin = null;
      $('pin-readout').textContent = 'Click the map where the photo was taken.';
    }
  } catch (error) {
    setStatus(error.message, true);
  }
}

function mapillaryForm(id) {
  const form = new FormData();
  form.append('mapillary_id', id);
  return form;
}

async function refreshRuns(selected = '') {
  const runs = await api('/api/runs').catch(() => []);
  const select = $('runs');
  select.replaceChildren(el('option', { value: '', text: runs.length ? 'Choose…' : 'None yet' }));
  for (const run of runs) {
    const stamp = `${run.name.slice(0, 4)}-${run.name.slice(4, 6)}-${run.name.slice(6, 8)} ${run.name.slice(9, 11)}:${run.name.slice(11, 13)}`;
    const label = `${stamp} · ${run.question}${run.explained ? '' : ' (no answer yet)'}`;
    select.append(el('option', { value: run.name, text: label, selected: run.name === selected }));
  }
}

async function init() {
  for (const button of document.querySelectorAll('.tabs button')) button.addEventListener('click', () => selectTab(button.dataset.tab));
  $('investigate').addEventListener('click', investigate);
  $('load-mapillary').addEventListener('click', () => {
    const id = $('mapillary').value.trim();
    if (id) loadPhoto(mapillaryForm(id));
  });
  $('file').addEventListener('change', () => {
    const file = $('file').files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    loadPhoto(form);
  });
  $('runs').addEventListener('change', () => { if ($('runs').value) loadRun($('runs').value); });
  $('overview').addEventListener('click', () => showOverview().catch((error) => setStatus(error.message, true)));
  for (const button of document.querySelectorAll('.stage-switch button')) button.addEventListener('click', () => showStage(button.dataset.view));
  let resize;
  window.addEventListener('resize', () => { clearTimeout(resize); resize = setTimeout(() => state.run && renderTimeline(state.run), 150); });

  const topics = await api('/api/topics').catch(() => []);
  $('topic').replaceChildren(el('option', { value: '', text: 'From the question' }),
    ...topics.map((topic) => el('option', { value: topic.key, text: topic.label })));
  const demos = await api('/api/demos').catch(() => []);
  for (const demo of demos) {
    $('demos').append(el('button', {
      type: 'button', text: demo.label,
      onclick: () => {
        $('question').value = demo.question;
        $('when').value = demo.when || '';
        $('mapillary').value = demo.mapillary_id;
        loadPhoto(mapillaryForm(demo.mapillary_id));
      },
    }));
  }
  await initMap();
  const fromLink = new URLSearchParams(location.hash.slice(1)).get('run');
  await refreshRuns(fromLink || '');
  const overview = await fetch('/api/batch').then((response) => response.ok).catch(() => false);
  $('overview').hidden = !overview;
  if (fromLink) loadRun(fromLink).catch(() => {});
  else if (overview && location.hash === '#overview') showOverview().catch(() => {});
}

init();
