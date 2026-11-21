import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import type { MeshPacket, ScenePacket } from '../scene/types';
import type { InitialView, ViewState } from '../input/protocol';
import { skyTexture, type Background } from './background';
import { frontView } from './frontView';
import { rasterSizedSvg } from './circleAppearance';
import { paintInTurn } from './paintQueue';
import { OrbitMotion } from './orbitMotion';
import { DoubleTap } from './doubleTap';
import { adaptResolution, FULL_RESOLUTION, type Resolution } from './motion';
import { BACK_GLASS, glassLayerPlan, type GlassLayerPlan } from '../scene/glassLayers';
import { axisLayers, axisLayout, chooseHinges, describeHinge, glassGeometry, glassLights, glintViews, planeZ,
  type AxisLayout, type GlassGeometry, type Hinge } from '../scene/glassAxes';
import { glassFragment, glassVertex, MAX_SLOTS } from './glassShader';
import type { Unpainted } from './Viewer';

export type GlassColor = 'none' | 'background' | 'layers';
export interface GlassSettings {
  angle: number; spacing: number; leaf: number; light: number; glassColor: GlassColor; sway: boolean;
  /** Keep turning at the release speed until touched (no friction). */ frictionless: boolean;}
export const GLASS_DEFAULTS: GlassSettings = {
  angle: 1, spacing: 1, leaf: 0.6, light: 0, glassColor: 'none', sway: false, frictionless: true,
};
/** The vessel and room the author judged in the trial (2026-11-20); not adjustable. */
export const GLASS_FIXED = {
  /** Front glass thickness, in short sides. */ front: 0.03,
  /** Room brightness against the background. */ room: 0.55,
  /** Silver stays neutral, not bluish. */ bluish: false,
  /** One small turn once every layer has appeared. */ swayOnce: true,
} as const;
/** The glass settings a view state remembers; sway is left out so a return never starts moving. */
export type RememberedGlass = Pick<GlassSettings, 'angle' | 'leaf' | 'light' | 'glassColor' | 'frictionless'>;

const PAINT_PIXELS = navigator.vendor.startsWith('Apple') ? 4 * 1024 * 1024 : 16 * 1024 * 1024;
const DEG = Math.PI / 180;
const smooth = (a: number, b: number, x: number) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

/** sRGB 0..1 of a CSS colour, as the 2D painter wrote it. */
function srgb(color: string): THREE.Vector3 {
  const c = new THREE.Color(color); const out = { r: 0, g: 0, b: 0 };
  c.getRGB(out, THREE.SRGBColorSpace); return new THREE.Vector3(out.r, out.g, out.b);
}
/** OKLCH chroma of an sRGB colour (the core's colourless line is 0.035). */
function chroma(v: THREE.Vector3): number {
  const lin = (x: number) => x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  const [r, g, b] = [lin(v.x), lin(v.y), lin(v.z)];
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
  return Math.hypot(A, B);
}
/** Absorption per unit length that keeps a colour's hue and leaves at least
 * `floor` of the light after `length`. The strongest channel is not reduced. */
function absorption(color: THREE.Vector3, floor: number, length: number): THREE.Vector3 {
  if (chroma(color) < 0.035 || length <= 0) return new THREE.Vector3();
  const m = Math.max(color.x, color.y, color.z, 1e-3);
  const t = color.clone().divideScalar(m), low = Math.min(t.x, t.y, t.z);
  const s = low < 1 ? Math.min(1, (1 - floor) / (1 - low)) : 0;
  return new THREE.Vector3(...[t.x, t.y, t.z].map(c => -Math.log(1 + (c - 1) * s) / length));
}

interface Layer { name: string | null; instructions: number[]; marks: MeshPacket[]; rect: [number, number, number, number];
  pixels: Uint8Array | null; average: THREE.Vector3; shown: number; pulse: number }

export class GlassViewer {
  readonly scene = new THREE.Scene();
  readonly renderer: THREE.WebGLRenderer;
  readonly controls: OrbitControls;
  camera: THREE.PerspectiveCamera | THREE.OrthographicCamera;
  projection: ViewState['projection'] = 'orthographic';
  background: Background = 'paint';
  settings: GlassSettings = { ...GLASS_DEFAULTS };
  readonly plan: GlassLayerPlan;
  readonly layers: Layer[];
  private readonly presenceSlot: boolean;
  private geometry!: GlassGeometry;
  private readonly layout: AxisLayout;
  /** Each layer's hinge, chosen once per work. */
  private readonly hinges: Hinge[];
  /** Sway: one petal per shining layer, from the front to where it glints and back. */
  private petals: { az: number; el: number }[] = [];
  private box: THREE.Mesh<THREE.BufferGeometry, THREE.ShaderMaterial>;
  private texture: THREE.DataArrayTexture;
  private size: number;
  private backgroundTexture: THREE.Texture | null = null;
  private referenceHeight = 2;
  private events = new AbortController();
  private resize: ResizeObserver;
  private frame = 0;
  private last = 0;
  private disposed = false;
  private painting: Promise<unknown> = Promise.resolve();
  // Motion: the shared turning, sway and the light that follows the pointer.
  private motion: OrbitMotion;
  private swayTime = 0;
  private lightTarget = [0, 0]; private lightNow = [0, 0];
  private swayMoved = 0;
  private frameTimes: number[] = [];
  private resolution = 1;
  private resolutionState: Resolution = FULL_RESOLUTION;
  private startPointer: [number, number] | null = null;
  /** Set by the page inside the iPhone and iPad apps: a double tap returns to 2D. */
  returnTo2D: (() => void) | null = null;
  private doubleTap = new DoubleTap();
  private lastPointerType = 'mouse';

  constructor(private host: HTMLElement, readonly packet: ScenePacket,
    private changed: (state: ViewState) => void,
    private selectedChanged: (data: Record<string, unknown> | null) => void,
    private failed: (reason: string) => void, private initialView?: InitialView) {
    try { this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: false }); }
    catch { throw new Error('webgl_unavailable'); }
    if (!this.renderer.capabilities.isWebGL2) throw new Error('webgl_unavailable');
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.setPixelRatio(this.pixelRatio());
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.NoToneMapping;
    const canvas = this.renderer.domElement;
    canvas.tabIndex = 0; canvas.setAttribute('aria-label', '3D');
    canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); this.failed('context_lost'); }, { signal: this.events.signal });
    host.append(canvas);
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.001, 1000);
    this.camera.position.set(0, 0, 10);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = false; this.controls.rotateSpeed = 0.6;
    this.controls.minZoom = 0.01; this.controls.maxZoom = 100;
    this.motion = new OrbitMotion(this.controls, () => this.camera, {
      frictionless: () => this.settings.frictionless, changed: () => { if (!this.disposed) this.changed(this.state()); },
      requestDraw: () => this.requestDraw(), started: () => { this.settings.sway = false; },
    });

    // Layers: chunks in paint order; marks keep the painter's order inside one.
    const painted = packet.meshes.filter(mesh => mesh.appearance);
    this.plan = glassLayerPlan(painted.map(mesh => mesh.sourceIndex), packet.chunks);
    this.layers = this.plan.names.map(name => ({ name, instructions: [], marks: [], rect: [0, 0, 1, 1], pixels: null,
      average: new THREE.Vector3(1, 1, 1), shown: 0, pulse: 0 }));
    const order = painted.map((mesh, i) => ({ mesh, i })).sort((a, b) => a.mesh.sourceIndex - b.mesh.sourceIndex || a.i - b.i);
    for (const { mesh } of order) {
      const layer = this.layers[this.plan.layerOf.get(mesh.sourceIndex)!];
      layer.marks.push(mesh);
      if (!layer.instructions.includes(mesh.sourceIndex)) layer.instructions.push(mesh.sourceIndex);
    }
    const [W, H] = packet.canvas;
    for (const layer of this.layers) {
      // The marks' paper area, so the raster spends its pixels where the leaf is.
      let x0 = W, y0 = H, x1 = 0, y1 = 0;
      for (const mark of layer.marks) {
        const [bx, by, bw, bh] = mark.appearance!.bounds;
        x0 = Math.min(x0, bx); y0 = Math.min(y0, by); x1 = Math.max(x1, bx + bw); y1 = Math.max(y1, by + bh);
      }
      x0 = Math.max(0, x0); y0 = Math.max(0, y0); x1 = Math.min(W, x1); y1 = Math.min(H, y1);
      if (!(x1 > x0 && y1 > y0)) { x0 = 0; y0 = 0; x1 = W; y1 = H; }
      layer.rect = [x0, y0, x1, y1];
    }
    // Hinges: from the marks' footprints, the same on every device; chosen once
    // (at plane angle 1, layer depth 1 and the light control 0, whatever the controls say).
    const footprint = axisLayers(this.layers.map(layer => layer.marks), packet.canvas);
    this.layout = axisLayout(footprint.grid, footprint.layers, packet.canvas);
    this.hinges = chooseHinges(this.layout);
    this.presenceSlot = !!packet.presenceSvg;
    const slots = this.layers.length + (this.presenceSlot ? 1 : 0);
    this.size = Math.max(64, Math.min(2048, Math.floor(Math.sqrt(PAINT_PIXELS / Math.max(1, slots)))));
    // Margin of two texels around each crop.
    for (const layer of this.layers) {
      const [x0, y0, x1, y1] = layer.rect, mx = 2 * (x1 - x0) / this.size, my = 2 * (y1 - y0) / this.size;
      layer.rect = [Math.max(0, x0 - mx), Math.max(0, y0 - my), Math.min(W, x1 + mx), Math.min(H, y1 + my)];
    }
    this.texture = new THREE.DataArrayTexture(new Uint8Array(this.size * this.size * 4 * Math.max(1, slots)), this.size, this.size, Math.max(1, slots));
    this.texture.format = THREE.RGBAFormat; this.texture.type = THREE.UnsignedByteType;
    this.texture.colorSpace = THREE.NoColorSpace;
    this.texture.minFilter = THREE.LinearMipmapLinearFilter; this.texture.magFilter = THREE.LinearFilter;
    this.texture.generateMipmaps = true; this.texture.premultiplyAlpha = false; this.texture.needsUpdate = true;

    const material = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3, vertexShader: glassVertex, fragmentShader: glassFragment, side: THREE.FrontSide,
      uniforms: {
        uLayers: { value: this.texture }, uLayerSize: { value: this.size }, uSlots: { value: slots },
        uPlane: { value: Array.from({ length: MAX_SLOTS }, () => new THREE.Vector4()) },
        uRect: { value: Array.from({ length: MAX_SLOTS }, () => new THREE.Vector4(0, 0, 1, 1)) },
        uSigma: { value: Array.from({ length: MAX_SLOTS }, () => new THREE.Vector3()) },
        uPulse: { value: new Array(MAX_SLOTS).fill(0) },
        uBox: { value: Array.from({ length: 6 }, () => new THREE.Vector4()) },
        uPresence: { value: 0 }, uSigmaAll: { value: new THREE.Vector3() },
        uOrtho: { value: true }, uViewDir: { value: new THREE.Vector3(0, 0, -1) }, uPixelWorld: { value: 0.001 },
        uWeight: { value: 0 }, uLeaf: { value: 0.6 }, uBluish: { value: false },
        uBg: { value: srgb(packet.background) }, uRoom: { value: 0.55 },
        uLightC: { value: [0, 1, 2].map(() => new THREE.Vector3()) }, uLightU: { value: [0, 1, 2].map(() => new THREE.Vector3()) },
        uLightV: { value: [0, 1, 2].map(() => new THREE.Vector3()) }, uLightSize: { value: [0, 1, 2].map(() => new THREE.Vector3()) },
        uLightLow: { value: 0.25 }, uBounces: { value: 4 },
      },
    });
    this.box = new THREE.Mesh(new THREE.BufferGeometry(), material);
    this.box.name = 'Glass block';
    this.scene.add(this.box);
    this.rebuild();

    this.resize = new ResizeObserver(() => this.resizeView());
    this.resize.observe(host);
    canvas.addEventListener('pointerdown', e => { this.startPointer = [e.clientX, e.clientY]; canvas.focus({ preventScroll: true }); this.lastPointerType = e.pointerType; this.motion.touch(); }, { signal: this.events.signal });
    canvas.addEventListener('pointerup', e => {
      const tapped = this.startPointer && e.button === 0
        && Math.hypot(e.clientX - this.startPointer[0], e.clientY - this.startPointer[1]) < (e.pointerType === 'touch' ? 10 : 4);
      this.startPointer = null;
      // On iPhone and iPad, a double tap returns to 2D.
      if (tapped && e.pointerType === 'touch' && this.returnTo2D && this.doubleTap.tap(e.timeStamp, e.clientX, e.clientY)) { this.returnTo2D(); return; }
      if (!tapped || e.pointerType !== 'touch') this.doubleTap.clear();
      // A tap that stopped the turning does not also select.
      if (tapped && !this.motion.haltedByTouch) this.pick(e);
    }, { signal: this.events.signal });
    canvas.addEventListener('pointermove', e => {
      if (this.motion.dragging || e.pointerType === 'touch') return;
      const rect = canvas.getBoundingClientRect();
      this.lightTarget = [((e.clientX - rect.left) / rect.width * 2 - 1), -((e.clientY - rect.top) / rect.height * 2 - 1)];
      this.requestDraw();
    }, { signal: this.events.signal });
    canvas.addEventListener('pointerleave', () => { this.lightTarget = [0, 0]; this.requestDraw(); }, { signal: this.events.signal });
    // A mouse's double click focuses, also on an iPad; a touch double tap is handled on pointerup.
    canvas.addEventListener('dblclick', () => { if (this.lastPointerType !== 'touch') this.focus(); }, { signal: this.events.signal });
    canvas.addEventListener('keydown', this.keyboard, { signal: this.events.signal });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { cancelAnimationFrame(this.frame); this.frame = 0; } else this.requestDraw();
    }, { signal: this.events.signal });
    this.resizeView(); this.match2D(); this.setBackground(this.background);
  }

  private pixelRatio() { return Math.min(window.devicePixelRatio || 1, 2) * this.resolution; }

  /** Planes, block and uniforms from the settings. Only uniforms and eight
   * vertices change, so the controls open the layers smoothly. */
  private rebuild() {
    const s = this.settings, [W, H] = this.packet.canvas, u = this.box.material.uniforms;
    this.geometry = glassGeometry(this.layout, this.hinges, s.angle, s.spacing, GLASS_FIXED.front, BACK_GLASS);
    const g = this.geometry;
    // Eight corners; a box keeps its winding when its z is moved.
    const box = new THREE.BoxGeometry(W, H, 1);
    const position = box.getAttribute('position');
    for (let i = 0; i < position.count; i++) position.setZ(i, position.getZ(i) > 0 ? g.front : g.back);
    box.computeBoundingBox(); box.computeBoundingSphere();
    this.box.geometry.dispose(); this.box.geometry = box;
    const planes = u.uPlane.value as THREE.Vector4[], rects = u.uRect.value as THREE.Vector4[];
    let slot = 0;
    u.uPresence.value = this.presenceSlot ? 1 : 0;
    if (this.presenceSlot) {
      planes[slot].set(0, 0, g.back + BACK_GLASS / 2, 1);
      rects[slot].set(-W / 2, -H / 2, W / 2, H / 2); slot++;
    }
    this.layers.forEach((layer, i) => {
      planes[slot].set(g.planes[i].gx, g.planes[i].gy, g.planes[i].c, layer.shown);
      const [x0, y0, x1, y1] = layer.rect;
      rects[slot].set(x0 - W / 2, H / 2 - y1, x1 - W / 2, H / 2 - y0); slot++;
    });
    const boxPlanes = u.uBox.value as THREE.Vector4[];
    boxPlanes[0].set(-1, 0, 0, W / 2); boxPlanes[1].set(1, 0, 0, W / 2);
    boxPlanes[2].set(0, -1, 0, H / 2); boxPlanes[3].set(0, 1, 0, H / 2);
    boxPlanes[4].set(0, 0, 1, g.front); boxPlanes[5].set(0, 0, -1, -g.back);
    // Glass colour: the hue of the background, or of each layer for the glass
    // in front of it; low chroma stays clear.
    const sigma = u.uSigma.value as THREE.Vector3[]; sigma.forEach(v => v.set(0, 0, 0));
    (u.uSigmaAll.value as THREE.Vector3).set(0, 0, 0);
    if (s.glassColor === 'background') {
      (u.uSigmaAll.value as THREE.Vector3).copy(absorption(srgb(this.packet.background), 0.75, g.front - g.back));
    } else if (s.glassColor === 'layers' && this.layers.length > 1) {
      // Each layer colours the glass between it and the nearest plane in
      // front; the strength comes from the thickest such glass on the paper.
      const floor = 0.7 ** (1 / (this.layers.length - 1)), base = this.presenceSlot ? 1 : 0;
      const thick = new Array(this.layers.length).fill(0);
      for (let a = 0; a <= 8; a++) for (let b = 0; b <= 8; b++) {
        const x = -W / 2 + W * a / 8, y = -H / 2 + H * b / 8, z = g.planes.map(p => planeZ(p, x, y));
        z.forEach((zi, i) => {
          const ahead = Math.min(...z.filter((zj, j) => j !== i && zj >= zi));
          if (Number.isFinite(ahead)) thick[i] = Math.max(thick[i], ahead - zi);
        });
      }
      this.layers.forEach((layer, i) => { if (thick[i] > 1e-4) sigma[base + i].copy(absorption(layer.average, floor, thick[i])); });
    }
    u.uLeaf.value = s.leaf; u.uBluish.value = GLASS_FIXED.bluish; u.uRoom.value = GLASS_FIXED.room;
    u.uBounces.value = GLASS_FIXED.front > 0.5 ? 6 : 4;
    this.placeLights();
    this.findPetals();
    this.requestDraw();
  }

  /** Sway visits each shining layer in paint order: the view nearest the
   * front where light shows on the layer's centroid. */
  private findPetals() {
    const lights = glassLights(this.packet.canvas, this.settings.light);
    this.petals = [];
    this.layers.forEach((_, i) => {
      const facts = this.layout.facts[i];
      if (!facts.sheen) return;
      const [x, y] = facts.centroid, plane = this.geometry.planes[i];
      const found = glintViews(lights, [x, y, planeZ(plane, x, y)], plane, 40, 2)[0];
      if (found) this.petals.push(found);
    });
  }

  /** A: tall, on the left, B: wide, above, D: square, lower right. A and D
   * follow the pointer and the light control. C: a soft glow from below. */
  private placeLights() {
    const u = this.box.material.uniforms;
    glassLights(this.packet.canvas, this.settings.light, [this.lightNow[0], this.lightNow[1]]).forEach((light, k) => {
      u.uLightC.value[k].set(...light.c); u.uLightU.value[k].set(...light.u); u.uLightV.value[k].set(...light.v);
      u.uLightSize.value[k].set(light.hu, light.hv, light.power);
    });
  }

  /** Whether a background colour has enough hue to tint the glass. */
  static hasHue(color: string) { return chroma(srgb(color)) >= 0.035; }

  get paintTotal() { return this.layers.reduce((n, layer) => n + layer.marks.length, 0) + (this.presenceSlot ? 1 : 0); }
  prepareShape() { /* The block is ready before any paint. */ }
  drawNow() { cancelAnimationFrame(this.frame); this.frame = 0; this.render(); }

  /** Each layer's marks, decoded at the layer's density and laid down in
   * paint order on one transparent raster; layers appear from the back. */
  paint(progress: (done: number, total: number) => void): Promise<Unpainted[]> {
    const total = this.paintTotal; let done = 0;
    const unpainted: Unpainted[] = [];
    const tick = () => { if (!this.disposed) progress(++done, total); };
    const run = (async () => {
      if (this.presenceSlot) {
        try { await this.paintSlot(0, null, [{ svg: this.packet.presenceSvg!, bounds: [0, 0, ...this.packet.canvas] as [number, number, number, number] }]); }
        catch (error) { unpainted.push({ role: 'presence', reason: String(error).slice(0, 200) }); }
        tick();
      }
      for (let i = 0; i < this.layers.length && !this.disposed; i++) {
        const layer = this.layers[i];
        const failures = await this.paintSlot((this.presenceSlot ? 1 : 0) + i, layer,
          layer.marks.map(mark => ({ svg: mark.appearance!.svg, bounds: mark.appearance!.bounds })), tick);
        for (const { index, error } of failures) {
          const mark = layer.marks[index];
          unpainted.push({ sourceIndex: mark.sourceIndex, performedIndex: mark.performedIndex, instanceIndex: mark.instanceIndex, role: mark.role, reason: String(error).slice(0, 200) });
        }
        this.reveal(i);
      }
      if (!this.disposed && GLASS_FIXED.swayOnce) this.motion.swayOnce(() => this.disposed);
      return unpainted;
    })();
    this.painting = run.catch(() => undefined);
    return run;
  }

  private async paintSlot(slot: number, layer: Layer | null, marks: { svg: string; bounds: [number, number, number, number] }[], tick = () => {}) {
    const S = this.size, [W, H] = this.packet.canvas;
    const [rx0, ry0, rx1, ry1] = layer ? layer.rect : [0, 0, W, H];
    const raster = document.createElement('canvas'); raster.width = S; raster.height = S;
    const context = raster.getContext('2d', { willReadFrequently: true })!;
    const decoded: (HTMLImageElement | null)[] = new Array(marks.length).fill(null);
    const geometry = marks.map(({ bounds: [bx, by, bw, bh] }) => {
      const x = (bx - rx0) / (rx1 - rx0) * S, y = (by - ry0) / (ry1 - ry0) * S;
      return [x, y, Math.max(1, bw / (rx1 - rx0) * S), Math.max(1, bh / (ry1 - ry0) * S)];
    });
    const failures = await paintInTurn(marks.map((_, i) => i), 4, async i => {
      try {
        const [, , w, h] = geometry[i];
        // The cropped layer occupies a square texture. Its world-space
        // rectangle restores the aspect ratio, so the raster must fill the slot.
        const url = URL.createObjectURL(new Blob([rasterSizedSvg(marks[i].svg, Math.ceil(w), Math.ceil(h), true)], { type: 'image/svg+xml' }));
        const image = new Image();
        let timer: ReturnType<typeof setTimeout> | undefined;
        try {
          await new Promise<void>((resolve, reject) => {
            timer = setTimeout(() => reject(new Error('glass_decode_timeout')), 5000);
            image.onload = () => resolve(); image.onerror = () => reject(new Error('glass_decode_failed'));
            image.src = url;
          });
          decoded[i] = image;
        } finally { clearTimeout(timer); URL.revokeObjectURL(url); }
      } finally { tick(); }
    }, () => this.disposed);
    // Lay the marks down in paint order, as the 2D painter composites them.
    marks.forEach((_, i) => { const image = decoded[i]; if (image) context.drawImage(image, ...geometry[i] as [number, number, number, number]); });
    const data = context.getImageData(0, 0, S, S).data;
    const premultiplied = new Uint8Array(data.length);
    let r = 0, g = 0, b = 0, a = 0;
    for (let p = 0; p < data.length; p += 4) {
      const alpha = data[p + 3] / 255;
      premultiplied[p] = Math.round(data[p] * alpha); premultiplied[p + 1] = Math.round(data[p + 1] * alpha);
      premultiplied[p + 2] = Math.round(data[p + 2] * alpha); premultiplied[p + 3] = data[p + 3];
      r += data[p] * alpha; g += data[p + 1] * alpha; b += data[p + 2] * alpha; a += alpha;
    }
    if (layer) { layer.pixels = premultiplied; if (a > 0) layer.average.set(r / a / 255, g / a / 255, b / a / 255); }
    (this.texture.image.data as Uint8Array).set(premultiplied, slot * S * S * 4);
    this.texture.needsUpdate = true;
    raster.width = raster.height = 1;
    decoded.forEach(image => { if (image) image.src = ''; });
    return failures.map(({ item, error }) => ({ index: item, error }));
  }

  private reveals: { layer: number; start: number }[] = [];
  private reveal(layer: number) {
    this.reveals.push({ layer, start: performance.now() });
    if (this.settings.glassColor === 'layers') this.rebuild();
    this.requestDraw();
  }

  private requestDraw() { if (!this.disposed && !document.hidden && !this.frame) this.frame = requestAnimationFrame(this.draw); }

  private draw = (time: number) => {
    this.frame = 0;
    if (this.disposed) return;
    const dt = Math.min(0.05, (time - this.last) / 1000 || 0); this.last = time;
    // Inertia (without friction it turns at the release speed until touched) and tweens.
    let animating = this.motion.step(dt);
    if (this.settings.sway && !this.motion.dragging) {
      this.swayTime += dt;
      // Petals: from the front to where each shining layer glints and back,
      // 6 seconds each, in paint order; the front shows the 2D picture between them.
      let az: number, el: number;
      if (this.petals.length) {
        const petal = this.petals[Math.floor(this.swayTime / 6) % this.petals.length];
        const a = (1 - Math.cos(2 * Math.PI * (this.swayTime % 6) / 6)) / 2;
        az = a * petal.az * DEG; el = a * petal.el * DEG;
      } else {
        az = (10 + 35 * Math.sin(2 * Math.PI * this.swayTime / 16)) * DEG; el = 6 * Math.sin(2 * Math.PI * this.swayTime / 23) * DEG;
      }
      const distance = this.camera.position.distanceTo(this.controls.target);
      this.camera.position.copy(this.controls.target).add(new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el)).multiplyScalar(distance));
      this.camera.lookAt(this.controls.target); this.controls.update();
      animating = true; this.swayMoved = performance.now();
    }
    // The light follows the pointer over about 0.15 seconds.
    const follow = 1 - Math.exp(-dt / 0.15);
    for (const k of [0, 1]) this.lightNow[k] += (this.lightTarget[k] - this.lightNow[k]) * follow;
    if (Math.abs(this.lightTarget[0] - this.lightNow[0]) + Math.abs(this.lightTarget[1] - this.lightNow[1]) > 1e-3) animating = true;
    this.placeLights();
    // Layers appear from the back over 0.25 seconds; a picked layer glows for 0.6.
    const now = performance.now();
    for (const r of this.reveals) { const k = Math.min(1, (now - r.start) / 250); this.layers[r.layer].shown = k; if (k < 1) animating = true; }
    this.reveals = this.reveals.filter(r => this.layers[r.layer].shown < 1);
    for (const layer of this.layers) if (layer.pulse > 0) { layer.pulse = Math.max(0, layer.pulse - dt / 0.6 * 0.5); animating = true; }
    this.adaptResolution(time);
    this.render();
    if (animating || now - this.lastMoved() < 200) this.requestDraw();
  };

  private lastMoved() { return Math.max(this.swayMoved, this.motion.moving); }
  /** Heavy frames while moving lower the drawing resolution and light ones
   * raise it again; it is full 0.15 seconds after the motion stops. */
  private adaptResolution(time: number) {
    const moving = performance.now() - this.lastMoved() < 150 || this.motion.dragging;
    let average: number | null = null;
    if (moving) {
      this.frameTimes.push(time); if (this.frameTimes.length > 11) this.frameTimes.shift();
      if (this.frameTimes.length === 11) average = (this.frameTimes[10] - this.frameTimes[0]) / 10;
    }
    const next = adaptResolution(this.resolutionState, average, moving, performance.now());
    if (next.value !== this.resolution) { this.resolution = next.value; this.applyResolution(); this.frameTimes = []; }
    this.resolutionState = next;
  }
  private applyResolution() { this.renderer.setPixelRatio(this.pixelRatio()); this.resizeView(false); }

  private render() {
    const u = this.box.material.uniforms, s = this.settings;
    let slot = this.presenceSlot ? 1 : 0;
    const planes = u.uPlane.value as THREE.Vector4[], pulse = u.uPulse.value as number[];
    for (const layer of this.layers) { planes[slot].w = layer.shown; pulse[slot] = layer.pulse; slot++; }
    const forward = new THREE.Vector3(); this.camera.getWorldDirection(forward);
    u.uOrtho.value = this.camera instanceof THREE.OrthographicCamera;
    u.uViewDir.value.copy(forward);
    // Front weight: sheen, mirrors and Fresnel fade out within 2-10 degrees of the front.
    u.uWeight.value = smooth(2 * DEG, 10 * DEG, forward.angleTo(new THREE.Vector3(0, 0, -1)));
    const heightPx = Math.max(1, this.renderer.domElement.height);
    if (this.camera instanceof THREE.OrthographicCamera) u.uPixelWorld.value = (this.camera.top - this.camera.bottom) / this.camera.zoom / heightPx;
    else u.uPixelWorld.value = 2 * this.camera.position.distanceTo(this.controls.target) * Math.tan(this.camera.fov * DEG / 2) / heightPx;
    u.uLeaf.value = s.leaf;
    this.renderer.render(this.scene, this.camera);
  }

  private resizeView(draw = true) {
    const width = Math.max(1, this.host.clientWidth), height = Math.max(1, this.host.clientHeight);
    this.renderer.setSize(width, height, false);
    const aspect = width / height;
    if (this.camera instanceof THREE.PerspectiveCamera) this.camera.aspect = aspect;
    else { const half = (this.camera.top - this.camera.bottom) / 2; this.camera.left = -half * aspect; this.camera.right = half * aspect; }
    this.camera.updateProjectionMatrix(); if (draw) this.requestDraw();
  }

  // The same controls as the solids --------------------------------------------

  private stateTimer = 0;
  private notify() { if (!this.stateTimer) this.stateTimer = window.setTimeout(() => { this.stateTimer = 0; if (!this.disposed) this.changed(this.state()); }, 120); }

  state(): ViewState & { glass: RememberedGlass; viewMode: 'glass' } {
    return { position: this.camera.position.toArray(), target: this.controls.target.toArray(), zoom: this.camera.zoom, projection: this.projection,
      depth: 1, layerSpacing: this.settings.spacing, background: this.background, referenceHeight: this.referenceHeight, displayZoom: this.displayZoom(),
      orthoHeight: this.camera instanceof THREE.OrthographicCamera ? this.camera.top - this.camera.bottom : 2,
      glass: { angle: this.settings.angle, leaf: this.settings.leaf, light: this.settings.light, glassColor: this.settings.glassColor, frictionless: this.settings.frictionless },
      viewMode: 'glass' };
  }
  restore(state: ViewState) {
    this.setProjection(state.projection);
    this.settings = { ...this.settings, ...(state.glass ?? {}), spacing: state.layerSpacing ?? this.settings.spacing, sway: false };
    this.setBackground(state.background ?? 'paint'); this.referenceHeight = state.referenceHeight ?? this.referenceHeight;
    this.camera.position.fromArray(state.position); this.controls.target.fromArray(state.target); this.camera.zoom = state.zoom;
    if (this.camera instanceof THREE.OrthographicCamera) { this.camera.top = state.orthoHeight / 2; this.camera.bottom = -state.orthoHeight / 2; this.resizeView(); }
    this.camera.updateProjectionMatrix(); this.controls.update(); this.rebuild();
  }
  set(change: Partial<GlassSettings>) { this.settings = { ...this.settings, ...change }; this.rebuild(); this.notify(); }

  fit() {
    const box = new THREE.Box3().setFromObject(this.box), sphere = box.getBoundingSphere(new THREE.Sphere());
    const radius = Math.max(0.005, sphere.radius) * 1.12, aspect = Math.max(0.01, this.host.clientWidth / Math.max(1, this.host.clientHeight));
    const direction = this.camera.position.clone().sub(this.controls.target).normalize();
    if (!direction.length()) direction.set(0, 0, 1);
    const halfAngle = Math.atan(Math.tan(Math.PI / 8) * Math.min(1, aspect));
    this.camera.position.copy(sphere.center).addScaledVector(direction, radius / Math.sin(halfAngle));
    this.controls.target.copy(sphere.center); this.camera.zoom = 1;
    if (this.camera instanceof THREE.OrthographicCamera) {
      const half = radius / Math.min(1, aspect);
      this.camera.top = half; this.camera.bottom = -half; this.camera.left = -half * aspect; this.camera.right = half * aspect;
    }
    this.camera.far = 1000; this.camera.updateProjectionMatrix(); this.controls.update(); this.notify(); this.requestDraw();
  }
  preset(name: string) {
    const directions: Record<string, [number, number, number]> = {
      front: [0, 0, 1], back: [0, 0, -1], left: [-1, 0, 0.0001], right: [1, 0, 0.0001], top: [0, 1, 0.0001], bottom: [0, -1, 0.0001], iso: [1, 0.8, 1.8],
    };
    this.camera.up.set(0, 1, 0); this.motion.turnTo(new THREE.Vector3(...directions[name]), 400);
  }
  match2D() {
    // A chosen direction ends any turning.
    this.motion.stop();
    this.setProjection('orthographic');
    const view = frontView(this.packet.canvas, this.host.clientWidth, this.host.clientHeight, this.initialView);
    this.referenceHeight = view.referenceHeight;
    const camera = this.camera as THREE.OrthographicCamera;
    camera.top = view.height / 2; camera.bottom = -view.height / 2; camera.zoom = 1;
    this.controls.target.fromArray(view.target);
    camera.position.copy(this.controls.target).add(new THREE.Vector3(0, 0, 20));
    camera.up.set(0, 1, 0); this.resizeView(); this.controls.update(); this.notify();
  }
  reset() {
    this.motion.stop();
    this.settings = { ...this.settings, angle: GLASS_DEFAULTS.angle, spacing: GLASS_DEFAULTS.spacing, leaf: GLASS_DEFAULTS.leaf, light: GLASS_DEFAULTS.light, sway: false };
    this.rebuild();
    const offset = this.camera.position.clone().sub(this.controls.target);
    if (this.camera instanceof THREE.OrthographicCamera && offset.angleTo(new THREE.Vector3(0, 0, 1)) > 1e-3) {
      this.motion.turnTo(new THREE.Vector3(0, 0, 1), 400, () => this.match2D());
    } else this.match2D();
  }
  private displayZoom(): number {
    const height = this.camera instanceof THREE.OrthographicCamera ? this.camera.top - this.camera.bottom
      : 2 * this.camera.position.distanceTo(this.controls.target) * Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    return this.referenceHeight * this.camera.zoom / height;
  }
  setZoom(value: number) {
    this.camera.zoom *= Math.max(0.25, Math.min(10, value)) / this.displayZoom();
    this.camera.updateProjectionMatrix(); this.controls.update(); this.notify(); this.requestDraw();
  }
  setBackground(value: Background) {
    this.backgroundTexture?.dispose(); this.backgroundTexture = null;
    this.background = value;
    if (value === 'sky' || value === 'stars') this.backgroundTexture = skyTexture(value);
    const fill = value === 'white' ? '#ffffff' : value === 'black' ? '#000000' : this.packet.background;
    this.scene.background = value === 'paint' || value === 'support' ? new THREE.Color(this.packet.background)
      : value === 'white' ? new THREE.Color(0xffffff) : value === 'black' ? new THREE.Color(0x000000) : this.backgroundTexture;
    this.box.material.uniforms.uBg.value = srgb(fill);
    this.notify(); this.requestDraw();
  }
  setProjection(projection: ViewState['projection']) {
    if (projection === this.projection) return;
    const previous = this.camera, direction = previous.position.clone().sub(this.controls.target);
    const height = previous instanceof THREE.PerspectiveCamera
      ? 2 * direction.length() * Math.tan(THREE.MathUtils.degToRad(previous.fov / 2)) / previous.zoom
      : (previous.top - previous.bottom) / previous.zoom;
    this.camera = projection === 'perspective' ? new THREE.PerspectiveCamera(45, 1, 0.001, 1000)
      : new THREE.OrthographicCamera(-1, 1, height / 2, -height / 2, 0.001, 1000);
    this.camera.position.copy(previous.position);
    if (projection === 'perspective') this.camera.position.copy(this.controls.target).addScaledVector(direction.normalize(), height / (2 * Math.tan(Math.PI / 8)));
    this.camera.up.copy(previous.up); this.projection = projection; this.controls.object = this.camera;
    this.resizeView(); this.controls.update(); this.notify();
  }
  pan(x: number, y: number) { this.controls.pan(x, y); this.controls.update(); this.notify(); this.requestDraw(); }
  zoom(inward: boolean) { if (inward) this.controls.dollyOut(1.15); else this.controls.dollyIn(1.15); this.controls.update(); this.notify(); this.requestDraw(); }
  setDepth(_: number) { /* Solids only. */ }
  setLayerSpacing(spacing: number) { this.set({ spacing }); }
  setOption(option: string, checked: boolean) { if (option === 'spin') { this.set({ sway: checked }); this.swayTime = 0; } this.requestDraw(); }

  // Picking: the first layer the light path meets through the front face.
  private selectedLayer = -1;
  private hitLayer(event: PointerEvent): number {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), this.camera);
    const hit = ray.intersectObject(this.box)[0];
    if (!hit || !hit.face) return -1;
    const normal = hit.face.normal.clone().transformDirection(this.box.matrixWorld);
    const d = refract(ray.ray.direction.clone(), normal, 1 / 1.5);
    if (!d) return -1;
    const [W, H] = this.packet.canvas, S = this.size;
    const hits = this.layers.map((_, i) => {
      const plane = this.geometry.planes[i], n = new THREE.Vector3(-plane.gx, -plane.gy, 1);
      const t = (plane.c - n.dot(hit.point)) / n.dot(d);
      return { i, t };
    }).filter(h => h.t > 0).sort((a, b) => a.t - b.t || b.i - a.i);
    for (const { i, t } of hits) {
      const p = hit.point.clone().addScaledVector(d, t), layer = this.layers[i];
      if (!layer.pixels || Math.abs(p.x) > W / 2 || Math.abs(p.y) > H / 2) continue;
      const [x0, y0, x1, y1] = layer.rect, cx = p.x + W / 2, cy = H / 2 - p.y;
      const u = (cx - x0) / (x1 - x0), v = (cy - y0) / (y1 - y0);
      if (u < 0 || u > 1 || v < 0 || v > 1) continue;
      const px = Math.min(S - 1, Math.floor(u * S)), py = Math.min(S - 1, Math.floor(v * S));
      if (layer.pixels[(py * S + px) * 4 + 3] > 25) return i;
    }
    return -1;
  }
  private pick(event: PointerEvent) {
    const i = this.hitLayer(event);
    this.selectedLayer = i;
    if (i >= 0) {
      const layer = this.layers[i]; layer.pulse = 0.5;
      this.selectedChanged({ glassLayer: i, name: layer.name, instructions: layer.instructions.map(n => n + 1) });
    } else this.selectedChanged(null);
    this.requestDraw();
  }
  /** Turn to the nearest view, in azimuth and elevation, where light A, B or D
   * shows on the selected layer's centroid, if there is one. */
  focus() {
    if (this.selectedLayer < 0) { this.fit(); return; }
    const facts = this.layout.facts[this.selectedLayer], plane = this.geometry.planes[this.selectedLayer];
    const [x, y] = facts.centroid;
    const views = glintViews(glassLights(this.packet.canvas, this.settings.light), [x, y, planeZ(plane, x, y)], plane, 60, 1);
    if (!views.length) { this.fit(); return; }
    const now = this.camera.position.clone().sub(this.controls.target).normalize();
    const toVector = (v: { az: number; el: number }) => new THREE.Vector3(Math.sin(v.az * DEG) * Math.cos(v.el * DEG), Math.sin(v.el * DEG), Math.cos(v.az * DEG) * Math.cos(v.el * DEG));
    let best = views[0], angle = Infinity;
    for (const view of views) { const a = toVector(view).angleTo(now); if (a < angle - 1e-12) { angle = a; best = view; } }
    this.motion.turnTo(toVector(best), 500);
  }

  private keyboard = (event: KeyboardEvent) => {
    const key = event.key.toLowerCase();
    if (key === 'f') this.fit();
    else if (key === 'r') this.reset();
    else if (key === '+' || key === '=') this.zoom(true);
    else if (key === '-') this.zoom(false);
    else if (key === '[' || key === ']') this.set({ angle: Math.max(0, Math.min(2, Math.round((this.settings.angle + (key === ']' ? 0.05 : -0.05)) * 100) / 100)) });
    else if (key.startsWith('arrow')) this.pan(key === 'arrowleft' ? 25 : key === 'arrowright' ? -25 : 0, key === 'arrowup' ? 25 : key === 'arrowdown' ? -25 : 0);
    else return;
    event.preventDefault();
  };

  async png(): Promise<Blob> {
    await this.painting;
    if (this.disposed) throw new Error('disposed');
    if (this.resolution !== 1) { this.resolution = 1; this.applyResolution(); }
    this.render();
    return new Promise((resolve, reject) => this.renderer.domElement.toBlob(blob => blob ? resolve(blob) : reject(new Error('empty_png')), 'image/png'));
  }
  /** GLB keeps the painted layer boards; the glass's light path is not in glTF. */
  async glb(): Promise<Blob> {
    await this.painting;
    if (this.disposed) throw new Error('disposed');
    const group = new THREE.Group(); group.name = 'Glass layers';
    const [W, H] = this.packet.canvas, S = this.size, disposables: { dispose(): void }[] = [];
    this.layers.forEach((layer, i) => {
      if (!layer.pixels) return;
      const plane = this.geometry.planes[i], [x0, y0, x1, y1] = layer.rect;
      const raster = document.createElement('canvas'); raster.width = S; raster.height = S;
      const image = raster.getContext('2d')!.createImageData(S, S);
      for (let p = 0; p < layer.pixels.length; p += 4) {
        const a = layer.pixels[p + 3] / 255;
        image.data[p] = a ? layer.pixels[p] / a : 0; image.data[p + 1] = a ? layer.pixels[p + 1] / a : 0; image.data[p + 2] = a ? layer.pixels[p + 2] / a : 0; image.data[p + 3] = layer.pixels[p + 3];
      }
      raster.getContext('2d')!.putImageData(image, 0, 0);
      const texture = new THREE.CanvasTexture(raster); texture.colorSpace = THREE.SRGBColorSpace;
      const material = new THREE.MeshBasicMaterial({ map: texture, transparent: true, side: THREE.DoubleSide });
      const geometry = new THREE.PlaneGeometry(x1 - x0, y1 - y0);
      const position = geometry.getAttribute('position');
      const cx = (x0 + x1) / 2 - W / 2, cy = H / 2 - (y0 + y1) / 2;
      for (let v = 0; v < position.count; v++) {
        const x = position.getX(v) + cx, y = position.getY(v) + cy; position.setXYZ(v, x, y, planeZ(plane, x, y));
      }
      const mesh = new THREE.Mesh(geometry, material); mesh.name = `layer-${i}${layer.name ? `-${layer.name}` : ''}`;
      mesh.userData = { glassLayer: i, chunk: layer.name, instructions: layer.instructions, hinge: describeHinge(this.hinges[i]) };
      group.add(mesh); disposables.push(geometry, material, texture);
    });
    group.userData = { layerMapping: 'glass-axes-v1', glass: { ...this.settings, ...GLASS_FIXED }, inputDigest: this.packet.inputDigest };
    try {
      const bytes = await new GLTFExporter().parseAsync(group, { binary: true });
      if (!(bytes instanceof ArrayBuffer)) throw new Error('invalid_glb');
      return new Blob([bytes], { type: 'model/gltf-binary' });
    } finally { disposables.forEach(item => item.dispose()); }
  }

  dispose() {
    if (this.disposed) return;
    this.changed(this.state()); this.disposed = true;
    cancelAnimationFrame(this.frame); clearTimeout(this.stateTimer);
    this.events.abort(); this.resize.disconnect();
    this.motion.dispose();
    this.controls.dispose();
    this.box.geometry.dispose(); this.box.material.dispose(); this.texture.dispose(); this.backgroundTexture?.dispose();
    this.renderer.renderLists.dispose(); this.renderer.dispose(); this.renderer.forceContextLoss(); this.renderer.domElement.remove();
  }
}

/** Snell's refraction of a unit direction through a surface with the given
 * outward normal; null on total internal reflection. */
function refract(d: THREE.Vector3, normal: THREE.Vector3, eta: number): THREE.Vector3 | null {
  const n = normal.clone(); let cos = -n.dot(d);
  if (cos < 0) { n.negate(); cos = -cos; }
  const k = 1 - eta * eta * (1 - cos * cos);
  if (k < 0) return null;
  return d.clone().multiplyScalar(eta).add(n.multiplyScalar(eta * cos - Math.sqrt(k))).normalize();
}
