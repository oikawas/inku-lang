import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { unpackMesh } from '../scene/build';
import type { MeshPacket, ScenePacket } from '../scene/types';
import type { InitialView, ViewState } from '../input/protocol';
import { skyTexture, type Background } from './background';
import { frontView } from './frontView';
import { applyPaint, rasterizePaint, type PaintAppearanceResources } from './circleAppearance';
import { preparePresence } from './presence';
import { objectDepth } from './objectDepth';
import { paintInTurn, paintOrder } from './paintQueue';
import { OrbitMotion } from './orbitMotion';
import { adaptResolution, frontWeight, FULL_RESOLUTION, solidsFold, turnBetween, type Resolution } from './motion';
import { foldedShare, smallestLayerGap } from '../scene/fold';
import { paperTone, shadeSolid, solidUniforms, type SolidUniforms } from './solidShading';

type Projection = ViewState['projection'];
export type SolidsSettings = NonNullable<ViewState['solids']>;
/** Turning keeps going until touched, the light comes from the upper left,
 * and layers open as the view turns away from the front. */
export const SOLIDS_DEFAULTS: SolidsSettings = { frictionless: true, light: 0, open: true };
const DEG = Math.PI / 180;
/** An object, or the presence plane, whose paint could not be prepared. */
export type Unpainted = { sourceIndex: number; performedIndex: number; instanceIndex: number; role: MeshPacket['role']; reason: string }
  | { role: 'presence'; reason: string };
const PAINT_CONCURRENCY = 4;
// WebKit (the macOS app and Safari) paints its heaviest works sooner with a quarter of the pixels.
const PAINT_PIXELS = navigator.vendor.startsWith('Apple') ? 4 * 1024 * 1024 : 16 * 1024 * 1024;
const PAINT_REDRAW_MS = 250;
export class Viewer {
  readonly scene = new THREE.Scene();
  readonly model = new THREE.Group();
  readonly renderer: THREE.WebGLRenderer;
  readonly controls: OrbitControls;
  readonly grid: THREE.GridHelper;
  readonly axes = new THREE.AxesHelper(0.3);
  readonly support: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshLambertMaterial>;
  camera: THREE.PerspectiveCamera | THREE.OrthographicCamera;
  selected: THREE.Object3D | null = null;
  projection: Projection = 'orthographic';
  depth = 1;
  layerSpacing = 1;
  background: Background = 'paint';
  private backgroundTexture: THREE.Texture | null = null;
  private referenceHeight = 2;
  private appearances = new Map<THREE.Mesh, PaintAppearanceResources>();
  private presence: Awaited<ReturnType<typeof preparePresence>> | null = null;
  private meshPackets = new Map<THREE.Mesh, MeshPacket>();
  private objectDepths = new Map<THREE.Mesh, ReturnType<typeof objectDepth>>();
  private selection = new THREE.BoxHelper(new THREE.Object3D(), 0x338bff);
  private resize: ResizeObserver;
  private events = new AbortController();
  private frame = 0;
  private stateTimer = 0;
  private painting: Promise<unknown> = Promise.resolve();
  private paintTimer = 0;
  private paintDrawn = 0;
  private disposed = false;
  private lastTime = 0;
  private startPointer: [number, number] | null = null;
  private flat = false;
  private wire = false;
  private sceneExtent = 1;
  settings: SolidsSettings = { ...SOLIDS_DEFAULTS };
  private sun = new THREE.DirectionalLight(0xffffff, 1);
  private paper: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>;
  private paperShadow: THREE.Mesh<THREE.PlaneGeometry, THREE.ShadowMaterial>;
  private paperColor = new THREE.Color();
  private shadowDirty = true;
  /** The pointer's place over the view (-1..1), and where the face light has got to. */
  private lightTarget = [0, 0]; private lightNow = [0, 0];
  private lastAzimuth = 0;
  private shared: SolidUniforms;
  private motion: OrbitMotion;
  /** How far the solids stand up from their layers; at the front they lie flat. */
  private fold = { inflate: -1, open: -1 };
  private frameTimes: number[] = [];
  private resolution: Resolution = FULL_RESOLUTION;

  constructor(private host: HTMLElement, readonly packet: ScenePacket,
    private changed: (state: ViewState) => void,
    private selectedChanged: (data: Record<string, unknown> | null) => void,
    private failed: (reason: string) => void, private initialView?: InitialView) {
    try { this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: false }); }
    catch { throw new Error('webgl_unavailable'); }
    this.shared = solidUniforms(packet.background);
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.setPixelRatio(this.pixelRatio());
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.NoToneMapping;
    const canvas = this.renderer.domElement;
    canvas.tabIndex = 0;
    canvas.setAttribute('aria-label', '3D');
    canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); this.failed('context_lost'); }, { signal: this.events.signal });
    this.host.append(canvas);
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.001, 1000);
    this.camera.position.set(0, 0, 10);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = false;
    this.controls.minDistance = 0.01; this.controls.maxDistance = 1000;
    this.controls.minZoom = 0.01; this.controls.maxZoom = 100;
    // The view state goes to the host when a drag ends or the turning stops,
    // not on every frame of a turn.
    this.motion = new OrbitMotion(this.controls, () => this.camera, {
      frictionless: () => this.settings.frictionless, changed: this.rememberNow, requestDraw: () => this.requestDraw(),
    });
    // Faces are shaded in their own shader (solidShading.ts); the one
    // directional light is the shadow's, fixed 10 degrees up and left of the
    // paper's normal, so a shadow falls close behind what casts it.
    this.sun.position.set(-0.12, 0.13, 1); this.scene.add(this.sun, this.sun.target);
    // Shadows: one soft map, drawn again only when the solids move against
    // each other (folding, opening, thickness), not while the view turns.
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.shadowMap.autoUpdate = false;
    this.sun.castShadow = true;
    const map = navigator.vendor.startsWith('Apple') ? 512 : 1024;
    this.sun.shadow.mapSize.set(map, map); this.sun.shadow.radius = 2.5; this.sun.shadow.bias = -0.0002;
    this.sun.shadow.intensity = 0;
    this.model.name = 'DDL solids';
    this.model.userData = { inputDigest: packet.inputDigest, mappingVersion: packet.mappingVersion,
      schemaDigest: packet.schemaDigest, engineVersion: packet.engineVersion, diagnostics: packet.diagnostics, recoveries: packet.recoveries, emptyPaths: packet.emptyPaths,
      layerMapping: 'paint-order-joints-v4', layerCount: packet.layerCount, layerSpacing: this.layerSpacing };
    const groups = new Map<number, THREE.Group>();
    for (const data of packet.meshes) {
      const mesh = new THREE.Mesh(unpackMesh(data), this.material(data.color, data.opacity));
      this.meshPackets.set(mesh, data);
      mesh.name = `${data.primitive}-${data.sourceIndex}-${data.performedIndex}-${data.instanceIndex}-${data.role}`;
      mesh.userData = { sourceIndex: data.sourceIndex, performedIndex: data.performedIndex, instanceIndex: data.instanceIndex,
        primitive: data.primitive, role: data.role, relatedSourceIndex: data.relatedSourceIndex,
        layerIndex: data.layerIndex, layerZ: data.layerZ, depthPath: data.depthPath,
        ...(packet.chunks?.[data.sourceIndex] ? { chunk: packet.chunks[data.sourceIndex] } : {}) };
      mesh.position.z = data.layerZ;
      // An outlined round is a transparent globe with paint on it; it would
      // cast the shadow of a full disc. A thin paint casts a thinner shadow.
      const round = data.primitive === 'circle' || data.primitive === 'ellipse';
      mesh.castShadow = !(round && !data.filled); mesh.receiveShadow = true;
      if (data.opacity < 1) mesh.customDepthMaterial = ditheredDepth(data.opacity);
      let group = groups.get(data.sourceIndex);
      if (!group) { group = new THREE.Group(); group.name = `instruction-${data.sourceIndex}`; groups.set(data.sourceIndex, group); this.model.add(group); }
      group.add(mesh);
    }
    this.scene.add(this.model);
    this.sceneExtent = Math.max(...packet.canvas, new THREE.Box3().setFromObject(this.model).getSize(new THREE.Vector3()).length() || 1);
    {
      const half = Math.max(...packet.canvas) * 0.75, shadow = this.sun.shadow.camera;
      shadow.left = -half; shadow.right = half; shadow.top = half; shadow.bottom = -half;
      shadow.near = 0.01; shadow.far = this.sceneExtent * 6;
      this.sun.position.set(-0.12, 0.13, 1).normalize().multiplyScalar(this.sceneExtent * 3); shadow.updateProjectionMatrix();
    }
    this.grid = new THREE.GridHelper(this.sceneExtent * 1.2, 20, 0x888888, 0xb0b0b0);
    this.grid.rotation.x = Math.PI / 2;
    this.grid.visible = false; this.axes.visible = false;
    const supportMaterial = new THREE.MeshLambertMaterial({ color: packet.background, side: THREE.DoubleSide });
    shadeSolid(supportMaterial, this.shared);
    this.support = new THREE.Mesh(new THREE.PlaneGeometry(...packet.canvas), supportMaterial);
    this.support.name = 'Canvas support';
    this.support.visible = false; this.support.receiveShadow = true;
    // The paper: the picture's ground as a sheet at the back, which shadows
    // fall on. At the front it is the same colour as the room around it.
    this.paper = new THREE.Mesh(new THREE.PlaneGeometry(...packet.canvas), new THREE.MeshBasicMaterial({ color: packet.background, side: THREE.FrontSide }));
    this.paperShadow = new THREE.Mesh(this.paper.geometry, new THREE.ShadowMaterial({ color: new THREE.Color(packet.background).multiplyScalar(0.35), side: THREE.FrontSide }));
    this.paper.name = 'Paper'; this.paperShadow.receiveShadow = true;
    this.scene.add(this.grid, this.axes, this.support, this.paper, this.paperShadow, this.selection);
    this.selection.visible = false;
    this.placeSupport();
    this.resize = new ResizeObserver(() => this.resizeView());
    this.resize.observe(host);
    canvas.addEventListener('pointerdown', e => {
      this.startPointer = [e.clientX, e.clientY]; canvas.focus({ preventScroll: true });
      if (this.motion.touch()) this.rememberNow();
    }, { signal: this.events.signal });
    canvas.addEventListener('pointerup', e => {
      // A tap that stopped the turning does not also select.
      if (this.startPointer && !this.motion.haltedByTouch && Math.hypot(e.clientX - this.startPointer[0], e.clientY - this.startPointer[1]) < 4 && e.button === 0) this.pick(e);
      this.startPointer = null;
    }, { signal: this.events.signal });
    canvas.addEventListener('pointermove', e => {
      this.pointerKind = e.pointerType;
      if (this.motion.dragging || e.pointerType !== 'mouse') return;
      const rect = canvas.getBoundingClientRect();
      this.lightTarget = [(e.clientX - rect.left) / rect.width * 2 - 1, -((e.clientY - rect.top) / rect.height * 2 - 1)];
      this.requestDraw();
    }, { signal: this.events.signal });
    canvas.addEventListener('pointerleave', () => { this.lightTarget = [0, 0]; this.requestDraw(); }, { signal: this.events.signal });
    canvas.addEventListener('dblclick', () => this.focus(), { signal: this.events.signal });
    canvas.addEventListener('keydown', this.keyboard, { signal: this.events.signal });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { cancelAnimationFrame(this.frame); this.frame = 0; }
      else this.requestDraw();
    }, { signal: this.events.signal });
    this.resizeView(); this.match2D(); this.setBackground(this.background);
  }

  private material(color: string | number | THREE.Color, opacity: number): THREE.Material {
    // Plain solids are shaded like painted ones, so paint arriving does not change their light.
    const material = new THREE.MeshLambertMaterial({ color, opacity, transparent: opacity < 1, depthWrite: opacity >= 1, wireframe: this.wire, side: THREE.FrontSide });
    shadeSolid(material, this.shared); return material;
  }

  /** Joint depths and the support for the plain solids, before any paint. */
  prepareShape() {
    for (const [mesh, packet] of this.meshPackets) this.objectDepths.set(mesh, objectDepth(mesh, packet));
    this.updateObjectDepths(); this.placeSupport();
  }
  /** Draw at once, so the shape is on screen before the host hears of it. */
  drawNow() {
    cancelAnimationFrame(this.frame); this.frame = 0;
    this.updateFold(); this.updateLight(); this.updateBoards(); this.renderShadows(); this.renderer.render(this.scene, this.camera);
  }

  /** The angle between the view and the front of the paper. */
  private frontAngle() { return this.camera.position.clone().sub(this.controls.target).angleTo(new THREE.Vector3(0, 0, 1)); }
  /** Fold the solids flat at the front and stand them up as the view turns.
   * Layers open with one scale of the whole model, so joint depths baked into
   * the line vertices open with their layers; a solid's own thickness does not
   * grow with the opening. True when anything changed. */
  private updateFold(force = false): boolean {
    const next = solidsFold(this.frontAngle(), this.settings.open);
    if (!force && Math.abs(next.inflate - this.fold.inflate) < 1e-4 && Math.abs(next.open - this.fold.open) < 1e-4) return false;
    this.fold = next; this.model.scale.z = next.open;
    for (const mesh of this.meshPackets.keys()) this.foldMesh(mesh);
    this.placeSupport(); if (this.selected) this.selection.setFromObject(this.selected);
    this.shadowDirty = true;
    return true;
  }
  /** At the front a solid keeps only a sliver of its thickness, thin enough
   * that it stays between the layers before and after it. */
  private foldMesh(mesh: THREE.Mesh) {
    if (this.meshPackets.get(mesh)?.depthPath) return;
    let size = this.solidDepths.get(mesh);
    if (size === undefined) {
      mesh.geometry.computeBoundingBox();
      const box = mesh.geometry.boundingBox!; size = box.max.z - box.min.z; this.solidDepths.set(mesh, size);
    }
    const share = foldedShare(size * this.depth, this.layerGap * this.layerSpacing);
    mesh.scale.z = this.depth * Math.max(this.fold.inflate, share) / Math.max(1, this.fold.open);
  }
  /** Shading grows over 2-20 degrees from the front. The face light sits up
   * and left; the light control turns it by up to 15 degrees either way. */
  private updateLight(dt = 0): boolean {
    const w = frontWeight(this.frontAngle(), 2, 20);
    this.shared.uWeight.value = w;
    // The light follows the pointer over about 0.15 seconds. On a touch screen
    // there is no pointer: the turning itself swings it a little, and it
    // settles back over 0.3 seconds.
    const azimuth = this.controls.getAzimuthalAngle();
    if (dt > 0 && this.pointerKind !== 'mouse') {
      const speed = turnBetween(this.lastAzimuth, azimuth) / dt;
      this.lightTarget = [Math.max(-1, Math.min(1, 0.12 * speed / Math.PI / (15 * DEG))), 0];
    }
    this.lastAzimuth = azimuth;
    const follow = 1 - Math.exp(-dt / (this.pointerKind === 'mouse' ? 0.15 : 0.3));
    for (const k of [0, 1]) this.lightNow[k] += (this.lightTarget[k] - this.lightNow[k]) * follow;
    const turn = (this.settings.light + this.lightNow[0]) * 15 * DEG;
    this.shared.uR.value.set(-0.24, 0.24, 0.94).normalize()
      .applyAxisAngle(new THREE.Vector3(1, 0, 0), -this.lightNow[1] * 8 * DEG).applyAxisAngle(new THREE.Vector3(0, 1, 0), turn);
    // Shadows and the room's darkening grow with the turn; the paper stays its colour.
    this.sun.shadow.intensity = 0.4 * w;
    if (this.scene.background instanceof THREE.Color && this.paper.visible) this.scene.background.copy(this.paperColor).multiplyScalar(1 - 0.28 * w);
    return Math.abs(this.lightTarget[0] - this.lightNow[0]) + Math.abs(this.lightTarget[1] - this.lightNow[1]) > 1e-3;
  }
  private pointerKind = 'mouse';
  /** A board stands at the back; seen from behind it would hide the whole
   * work, so it is not drawn then. It turns edge-on at the switch. */
  private updateBoards() {
    for (const [mesh, packet] of this.meshPackets) {
      if (!packet.board || packet.board < 0.5) continue;
      const visible = this.camera.position.z >= mesh.getWorldPosition(this.scratch).z;
      if (visible !== mesh.visible) { mesh.visible = visible; this.shadowDirty = true; }
    }
  }
  private scratch = new THREE.Vector3();
  private solidDepths = new Map<THREE.Mesh, number>();
  private get layerGap() { return this.gap ??= smallestLayerGap(this.packet.meshes.map(mesh => mesh.layerZ)); }
  private gap: number | undefined;
  get paintTotal() { return (this.packet.presenceSvg ? 1 : 0) + this.packet.meshes.filter(packet => packet.appearance).length; }

  /** Paint the shown solids: the presence plane first, then marks from the
   * front layer back. A mark whose paint fails keeps its plain color. */
  paint(progress: (done: number, total: number) => void): Promise<Unpainted[]> {
    const marks = paintOrder([...this.meshPackets].filter(([, packet]) => packet.appearance), ([, packet]) => packet.layerZ);
    const tasks = this.packet.presenceSvg ? [null, ...marks] : marks;
    // Pixels go by area: a board as large as the paper gets more than a dot.
    const area = (packet: MeshPacket) => packet.appearance!.bounds[2] * packet.appearance!.bounds[3];
    const total = marks.reduce((sum, [, packet]) => sum + area(packet), 0) || 1;
    const sideOf = (packet: MeshPacket) => Math.max(32, Math.min(1024, Math.floor(Math.sqrt(PAINT_PIXELS * area(packet) / total))));
    let done = 0;
    // Decodes run in turn anyway. A few at a time start each deadline with
    // its own decode, rather than letting queued marks expire while waiting.
    const painting = paintInTurn(tasks, PAINT_CONCURRENCY, async task => {
      try { await (task ? this.paintMark(task[0], task[1], sideOf(task[1])) : this.paintPresence()); }
      finally { if (!this.disposed) progress(++done, tasks.length); }
    }, () => this.disposed).then(failures => {
      const reasons = new Map(failures.map(({ item, error }) => [item?.[1] ?? null,
        (error instanceof Error && error.message ? error.message : String(error)).slice(0, 200)]));
      const unpainted: Unpainted[] = [
        ...reasons.has(null) ? [{ role: 'presence' as const, reason: reasons.get(null)! }] : [],
        ...this.packet.meshes.filter(packet => reasons.has(packet)).map(packet => ({ sourceIndex: packet.sourceIndex,
          performedIndex: packet.performedIndex, instanceIndex: packet.instanceIndex, role: packet.role, reason: reasons.get(packet)! })),
      ];
      if (!this.disposed) {
        if (unpainted.length) this.model.userData.unpaintedObjects = unpainted;
        clearTimeout(this.paintTimer); this.paintTimer = 0;
        this.placeSupport(); this.requestDraw();
        // At the front the solids lie flat like the 2D picture; one small turn
        // shows that they stand up.
        this.motion.swayOnce(() => this.disposed);
      }
      return unpainted;
    });
    this.painting = painting.catch(() => undefined);
    return painting;
  }

  private async paintPresence() {
    const presence = await preparePresence(this.packet.presenceSvg!, this.packet.canvas);
    if (this.disposed) { presence.dispose(); return; }
    this.presence = presence; this.scene.add(presence.mesh); this.placeSupport(); this.paintedDraw();
  }

  private async paintMark(mesh: THREE.Mesh, packet: MeshPacket, maxSide: number) {
    const painted = await rasterizePaint(packet, maxSide);
    if (!painted) return;
    if (this.disposed) { painted.dispose(); return; }
    // Paint maps the line's own Z; its joint depth returns on the new vertices.
    if (packet.depthPath) this.objectDepths.get(mesh)?.(1, 0);
    const old = mesh.material as THREE.Material;
    try {
      const resource = applyPaint(mesh, packet, this.packet.canvas, painted, this.shared);
      old.dispose(); resource.materials.forEach(material => { material.wireframe = this.wire; });
      this.appearances.set(mesh, resource);
    } catch (error) { painted.dispose(); throw error; }
    finally {
      const update = objectDepth(mesh, packet); this.objectDepths.set(mesh, update); update(this.depth, this.layerSpacing); this.foldMesh(mesh); this.shadowDirty = true;
      if (this.selected === mesh) this.selection.setFromObject(mesh);
      this.paintedDraw();
    }
  }

  /** Paint redraws at most every 0.25 seconds; view changes still draw at once. */
  private paintedDraw() {
    if (this.paintTimer || this.disposed) return;
    this.paintTimer = window.setTimeout(() => {
      this.paintTimer = 0; this.paintDrawn = performance.now(); this.requestDraw();
    }, Math.max(0, this.paintDrawn + PAINT_REDRAW_MS - performance.now()));
  }

  private controlChanged = () => {
    this.requestDraw();
    if (!this.stateTimer) this.stateTimer = window.setTimeout(() => { this.stateTimer = 0; if (!this.disposed) this.changed(this.state()); }, 120);
  };

  private resizeView() {
    const width = Math.max(1, this.host.clientWidth), height = Math.max(1, this.host.clientHeight);
    this.renderer.setSize(width, height, false);
    const aspect = width / height;
    if (this.camera instanceof THREE.PerspectiveCamera) this.camera.aspect = aspect;
    else { const half = (this.camera.top - this.camera.bottom) / 2; this.camera.left = -half * aspect; this.camera.right = half * aspect; }
    this.camera.updateProjectionMatrix(); this.requestDraw();
  }

  private requestDraw() { if (!this.disposed && !document.hidden && !this.frame) this.frame = requestAnimationFrame(this.draw); }
  private draw = (time: number) => {
    this.frame = 0;
    if (this.disposed) return;
    const dt = Math.min(0.05, (time - this.lastTime) / 1000 || 0); this.lastTime = time;
    let animating = this.motion.step(dt);
    this.updateFold(); if (this.updateLight(dt)) animating = true; this.updateBoards();
    this.adaptResolution(time);
    this.renderShadows();
    this.renderer.render(this.scene, this.camera);
    if (animating || performance.now() - this.motion.moving < 200) this.requestDraw();
  };

  private pixelRatio() { return Math.min(window.devicePixelRatio || 1, 2) * this.resolution.value; }
  /** Heavy frames while moving lower the drawing resolution and light ones
   * raise it again; it is full 0.15 seconds after the motion stops. */
  private adaptResolution(time: number) {
    const moving = performance.now() - this.motion.moving < 150 || this.motion.dragging;
    let average: number | null = null;
    if (moving) {
      this.frameTimes.push(time); if (this.frameTimes.length > 11) this.frameTimes.shift();
      if (this.frameTimes.length === 11) average = (this.frameTimes[10] - this.frameTimes[0]) / 10;
    }
    const next = adaptResolution(this.resolution, average, moving, performance.now());
    const changed = next.value !== this.resolution.value;
    this.resolution = next;
    if (changed) { this.frameTimes = []; this.renderer.setPixelRatio(this.pixelRatio()); this.resizeView(); }
  }

  private rememberNow = () => { if (!this.disposed) this.changed(this.state()); };
  /** Whether the automatic rotation is on; a touch ends it. */
  get spinning() { return this.motion.spinning; }
  set(change: Partial<SolidsSettings>) {
    this.settings = { ...this.settings, ...change };
    this.updateFold(true); this.controlChanged();
  }
  state(): ViewState { return { position: this.camera.position.toArray(), target: this.controls.target.toArray(), zoom: this.camera.zoom, projection: this.projection, depth: this.depth,
    layerSpacing: this.layerSpacing, background: this.background, referenceHeight: this.referenceHeight, displayZoom: this.displayZoom(),
    orthoHeight: this.camera instanceof THREE.OrthographicCamera ? this.camera.top - this.camera.bottom : 2, viewMode: 'solids',
    solids: { ...this.settings } }; }

  restore(state: ViewState) {
    if (state.solids) this.settings = { ...this.settings, ...state.solids };
    this.setProjection(state.projection); this.setDepth(state.depth); this.setLayerSpacing(state.layerSpacing ?? 1);
    this.setBackground(state.background ?? 'paint'); this.referenceHeight = state.referenceHeight ?? this.referenceHeight;
    this.camera.position.fromArray(state.position); this.controls.target.fromArray(state.target); this.camera.zoom = state.zoom;
    if (this.camera instanceof THREE.OrthographicCamera) {
      this.camera.top = state.orthoHeight / 2; this.camera.bottom = -state.orthoHeight / 2; this.resizeView();
    }
    this.camera.updateProjectionMatrix(); this.controls.update(); this.requestDraw();
  }

  fit(object: THREE.Object3D = this.model) {
    const box = new THREE.Box3().setFromObject(object);
    if (box.isEmpty()) box.setFromCenterAndSize(new THREE.Vector3(), new THREE.Vector3(...this.packet.canvas, 0.01));
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const radius = Math.max(0.005, sphere.radius) * 1.12;
    const direction = this.camera.position.clone().sub(this.controls.target).normalize();
    if (!direction.length()) direction.set(0, 0, 1);
    const aspect = Math.max(0.01, this.host.clientWidth / Math.max(1, this.host.clientHeight));
    const halfAngle = Math.atan(Math.tan(Math.PI / 8) * Math.min(1, aspect));
    this.camera.position.copy(sphere.center).addScaledVector(direction, radius / Math.sin(halfAngle));
    this.controls.target.copy(sphere.center); this.camera.zoom = 1;
    if (this.camera instanceof THREE.OrthographicCamera) {
      const half = radius / Math.min(1, aspect);
      this.camera.top = half; this.camera.bottom = -half; this.camera.left = -half * aspect; this.camera.right = half * aspect;
    }
    this.camera.far = Math.max(100, this.sceneExtent * 100); this.camera.updateProjectionMatrix();
    this.controls.update(); this.controlChanged();
  }

  preset(name: string) {
    const directions: Record<string, [number, number, number]> = {
      front: [0, 0, 1], back: [0, 0, -1], left: [-1, 0, 0], right: [1, 0, 0], top: [0, 1, 0.00001], bottom: [0, -1, 0.00001], iso: [1, 0.8, 1.8],
    };
    this.camera.up.set(0, 1, 0);
    // Turn there smoothly, then frame the work; a chosen direction ends any turning.
    this.motion.turnTo(new THREE.Vector3(...directions[name]), 400, () => this.fit());
  }

  match2D() {
    this.motion.stop();
    this.setProjection('orthographic');
    const view = frontView(this.packet.canvas, this.host.clientWidth, this.host.clientHeight, this.initialView);
    this.referenceHeight = view.referenceHeight;
    const camera = this.camera as THREE.OrthographicCamera;
    camera.top = view.height / 2; camera.bottom = -view.height / 2; camera.zoom = 1;
    this.controls.target.fromArray(view.target);
    camera.position.copy(this.controls.target).add(new THREE.Vector3(0, 0, this.sceneExtent * 4 + 1));
    camera.up.set(0, 1, 0); this.resizeView(); this.controls.update(); this.controlChanged();
  }
  reset() { this.motion.stop(); this.setDepth(1); this.setLayerSpacing(1); this.match2D(); }
  private displayZoom(): number {
    const height = this.camera instanceof THREE.OrthographicCamera ? this.camera.top - this.camera.bottom
      : 2 * this.camera.position.distanceTo(this.controls.target) * Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    return this.referenceHeight * this.camera.zoom / height;
  }
  setZoom(value: number) {
    this.camera.zoom *= Math.max(0.25, Math.min(10, value)) / this.displayZoom();
    this.camera.updateProjectionMatrix(); this.controls.update(); this.controlChanged();
  }
  setBackground(value: Background) {
    this.backgroundTexture?.dispose(); this.backgroundTexture = null;
    this.background = value; this.support.visible = value === 'support';
    if (value === 'sky' || value === 'stars') this.backgroundTexture = skyTexture(value);
    // A plain ground is a sheet of paper at the back; the room round it darkens as the view turns.
    const plain = value === 'paint' ? this.packet.background : value === 'white' ? '#ffffff' : value === 'black' ? '#000000' : null;
    this.paper.visible = this.paperShadow.visible = plain !== null;
    if (plain !== null) {
      this.paperColor.set(plain); this.paper.material.color.copy(this.paperColor);
      this.paperShadow.material.color.copy(this.paperColor).multiplyScalar(0.35);
      this.shared.uTone.value.copy(paperTone(plain));
    }
    this.scene.background = plain !== null ? this.paperColor.clone() : this.backgroundTexture;
    this.updateLight(); this.shadowDirty = true;
    this.controlChanged();
  }

  setProjection(projection: Projection) {
    if (projection === this.projection) return;
    const previous = this.camera;
    const direction = previous.position.clone().sub(this.controls.target);
    const height = previous instanceof THREE.PerspectiveCamera
      ? 2 * direction.length() * Math.tan(THREE.MathUtils.degToRad(previous.fov / 2)) / previous.zoom
      : (previous.top - previous.bottom) / previous.zoom;
    this.camera = projection === 'perspective'
      ? new THREE.PerspectiveCamera(45, 1, previous.near, previous.far)
      : new THREE.OrthographicCamera(-1, 1, height / 2, -height / 2, previous.near, previous.far);
    this.camera.position.copy(previous.position);
    if (projection === 'perspective') this.camera.position.copy(this.controls.target)
      .addScaledVector(direction.normalize(), height / (2 * Math.tan(Math.PI / 8)));
    this.camera.up.copy(previous.up); this.projection = projection;
    this.controls.object = this.camera;
    this.resizeView(); this.controls.update(); this.controlChanged();
  }

  pan(x: number, y: number) { this.controls.pan(x, y); this.controls.update(); this.controlChanged(); }
  zoom(inward: boolean) {
    if (inward) this.controls.dollyOut(1.15); else this.controls.dollyIn(1.15);
    this.controls.update(); this.controlChanged();
  }

  setDepth(depth: number) {
    this.depth = Math.max(0.1, Math.min(3, depth));
    this.updateObjectDepths();
    this.placeSupport(); if (this.selected) this.selection.setFromObject(this.selected); this.controlChanged();
  }
  setLayerSpacing(spacing: number) {
    this.layerSpacing = Math.max(0, Math.min(3, spacing));
    this.model.userData.layerSpacing = this.layerSpacing;
    this.updateObjectDepths();
    this.placeSupport(); if (this.selected) this.selection.setFromObject(this.selected); this.controlChanged();
  }
  private updateObjectDepths() {
    for (const update of this.objectDepths.values()) update(this.depth, this.layerSpacing);
    for (const mesh of this.objectDepths.keys()) this.foldMesh(mesh);
    this.shadowDirty = true;
  }
  /** Draw the shadow map again when the solids have moved against each other.
   * At the front, where shadows are not shown, it waits for the turn. */
  private renderShadows() {
    // The map is drawn once at the start as well: until then the shaders would
    // sample a shadow texture that does not exist yet (a WebGL warning per draw).
    const first = !this.sun.shadow.map;
    if (first || (this.shadowDirty && this.sun.shadow.intensity > 0 && !this.flat)) { this.renderer.shadowMap.needsUpdate = true; this.shadowDirty = false; }
  }
  private placeSupport() {
    const box = new THREE.Box3().setFromObject(this.model);
    const z = (box.isEmpty() ? 0 : box.min.z) - 0.02;
    if (this.presence) this.presence.mesh.position.z = z + 0.01;
    this.support.position.z = z; this.grid.position.z = z - 0.001; this.axes.position.z = z;
    this.paper.position.z = z - 0.004; this.paperShadow.position.z = z - 0.002;
  }

  setOption(option: string, checked: boolean) {
    if (option === 'grid') this.grid.visible = checked;
    if (option === 'axes') this.axes.visible = checked;
    // The automatic rotation is a steady turn of 6 degrees a second.
    if (option === 'spin') this.motion.spin(checked ? 6 * DEG : 0);
    // Flat colour turns the shading and shadows off in every solid at once.
    if (option === 'unlit') { this.flat = checked; this.shared.uLit.value = checked ? 0 : 1; }
    if (option === 'wire') {
      this.wire = checked;
      this.model.traverse(object => {
        if (object instanceof THREE.Mesh) (Array.isArray(object.material) ? object.material : [object.material]).forEach(material => { material.wireframe = checked; });
      });
    }
    this.requestDraw();
  }

  private pick(event: PointerEvent) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), this.camera);
    this.model.updateMatrixWorld(true);
    this.selected = ray.intersectObject(this.model, true)[0]?.object ?? null;
    this.selection.visible = !!this.selected;
    if (this.selected) this.selection.setFromObject(this.selected);
    this.selectedChanged(this.selected?.userData ?? null); this.requestDraw();
  }
  focus() { if (this.selected) this.fit(this.selected); }

  private keyboard = (event: KeyboardEvent) => {
    const key = event.key.toLowerCase();
    if (key === 'f') this.fit();
    else if (key === 'r') this.reset();
    else if (key === '+' || key === '=') this.zoom(true);
    else if (key === '-') this.zoom(false);
    else if (key.startsWith('arrow')) this.pan(key === 'arrowleft' ? 25 : key === 'arrowright' ? -25 : 0, key === 'arrowup' ? 25 : key === 'arrowdown' ? -25 : 0);
    else return;
    event.preventDefault(); this.controls.update(); this.controlChanged();
  };

  async png(): Promise<Blob> {
    await this.painting;
    if (this.disposed) throw new Error('disposed');
    if (this.resolution.value !== 1) { this.resolution = FULL_RESOLUTION; this.renderer.setPixelRatio(this.pixelRatio()); this.resizeView(); }
    this.updateFold(); this.updateLight(); this.updateBoards(); this.renderShadows(); this.renderer.render(this.scene, this.camera);
    return new Promise((resolve, reject) => this.renderer.domElement.toBlob(blob => blob ? resolve(blob) : reject(new Error('empty_png')), 'image/png'));
  }
  async glb(): Promise<Blob> {
    // Geometry, current depth, source IDs and color/opacity; guides and selection stay in the viewer.
    await this.painting;
    if (this.disposed) throw new Error('disposed');
    // The file holds the solids fully stood up and not opened, whatever the view.
    const fold = this.fold; this.fold = { inflate: 1, open: 1 };
    this.model.scale.z = 1; for (const mesh of this.meshPackets.keys()) this.foldMesh(mesh);
    this.placeSupport();
    const group = new THREE.Group(); group.add(this.model.clone(true));
    if (this.presence) group.add(this.presence.mesh.clone());
    if (this.support.visible) group.add(this.support.clone());
    this.fold = fold; this.updateFold(true);
    // glTF has no place for the view's own shading: the file carries plain
    // materials with the paint and colour, as the front of the work shows them.
    const plain: THREE.Material[] = [];
    group.traverse(object => {
      const mesh = object as THREE.Mesh;
      if (!mesh.isMesh || !(mesh.material instanceof THREE.MeshLambertMaterial)) return;
      const from = mesh.material, to = new THREE.MeshBasicMaterial({ color: from.color, map: from.map, opacity: from.opacity,
        transparent: from.transparent, alphaTest: from.alphaTest, side: from.side, name: from.name });
      mesh.material = to; plain.push(to);
    });
    try {
      const bytes = await new GLTFExporter().parseAsync(group, { binary: true, onlyVisible: true });
      if (!(bytes instanceof ArrayBuffer)) throw new Error('invalid_glb');
      return new Blob([bytes], { type: 'model/gltf-binary' });
    } finally { plain.forEach(material => material.dispose()); }
  }

  dispose() {
    if (this.disposed) return;
    this.changed(this.state()); this.disposed = true;
    cancelAnimationFrame(this.frame); clearTimeout(this.stateTimer); clearTimeout(this.paintTimer);
    this.events.abort(); this.resize.disconnect(); this.motion.dispose(); this.controls.dispose();
    const geometries = new Set<THREE.BufferGeometry>(), materials = new Set<THREE.Material>();
    this.scene.traverse(object => {
      const drawable = object as THREE.Mesh;
      if (drawable.geometry) geometries.add(drawable.geometry);
      if (drawable.material) (Array.isArray(drawable.material) ? drawable.material : [drawable.material]).forEach(m => materials.add(m));
    });
    geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); this.scene.clear();
    this.backgroundTexture?.dispose();
    this.presence?.dispose(); this.presence = null;
    this.appearances.forEach(resource => resource.dispose()); this.appearances.clear();
    this.meshPackets.clear();
    this.renderer.renderLists.dispose(); this.renderer.dispose(); this.renderer.forceContextLoss(); this.renderer.domElement.remove();
  }
}

/** A thin paint casts a thinner shadow: the depth pass keeps only a share of
 * its pixels, in an ordered 4 x 4 pattern that the soft filter smooths. */
function ditheredDepth(opacity: number): THREE.MeshDepthMaterial {
  const material = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking });
  material.onBeforeCompile = shader => {
    shader.uniforms.uOpacity = { value: opacity };
    shader.fragmentShader = shader.fragmentShader.replace('void main() {', `uniform float uOpacity;
void main() {
  {
    int x = int( mod( gl_FragCoord.x, 4.0 ) ), y = int( mod( gl_FragCoord.y, 4.0 ) );
    int bayer[ 16 ] = int[ 16 ]( 0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5 );
    if ( uOpacity * 16.0 <= float( bayer[ y * 4 + x ] ) + 0.5 ) discard;
  }`);
  };
  material.customProgramCacheKey = () => `inku-dither-${opacity.toFixed(3)}`;
  return material;
}
