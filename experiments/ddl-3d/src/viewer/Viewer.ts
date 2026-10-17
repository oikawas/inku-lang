import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { unpackMesh } from '../scene/build';
import type { MeshPacket, ScenePacket } from '../scene/types';
import type { InitialView, ViewState } from '../input/protocol';
import { skyTexture, type Background } from './background';
import { frontView } from './frontView';
import { prepareCircleAppearance, type CircleAppearanceResources } from './circleAppearance';

type Projection = ViewState['projection'];
export class Viewer {
  readonly scene = new THREE.Scene();
  readonly model = new THREE.Group();
  readonly renderer: THREE.WebGLRenderer;
  readonly controls: OrbitControls;
  readonly grid: THREE.GridHelper;
  readonly axes = new THREE.AxesHelper(0.3);
  readonly support: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshStandardMaterial>;
  camera: THREE.PerspectiveCamera | THREE.OrthographicCamera;
  selected: THREE.Object3D | null = null;
  projection: Projection = 'orthographic';
  depth = 1;
  layerSpacing = 1;
  background: Background = 'none';
  private backgroundTexture: THREE.Texture | null = null;
  private referenceHeight = 2;
  private appearances = new Map<THREE.Mesh, CircleAppearanceResources>();
  private meshPackets = new Map<THREE.Mesh, MeshPacket>();
  private selection = new THREE.BoxHelper(new THREE.Object3D(), 0x338bff);
  private resize: ResizeObserver;
  private events = new AbortController();
  private frame = 0;
  private stateTimer = 0;
  private disposed = false;
  private lastTime = 0;
  private startPointer: [number, number] | null = null;
  private flat = false;
  private wire = false;
  private sceneExtent = 1;

  constructor(private host: HTMLElement, readonly packet: ScenePacket,
    private changed: (state: ViewState) => void,
    private selectedChanged: (data: Record<string, unknown> | null) => void,
    private failed: (reason: string) => void, private initialView?: InitialView) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: false });
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
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
    this.controls.autoRotateSpeed = 1;
    this.controls.addEventListener('change', this.controlChanged);
    this.controls.addEventListener('end', this.rememberNow);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8c8c8c, 2));
    const key = new THREE.DirectionalLight(0xffffff, 2.4); key.position.set(-2, 3, 4); this.scene.add(key);
    this.model.name = 'DDL solids';
    this.model.userData = { inputDigest: packet.inputDigest, mappingVersion: packet.mappingVersion,
      schemaDigest: packet.schemaDigest, engineVersion: packet.engineVersion, diagnostics: packet.diagnostics, recoveries: packet.recoveries,
      layerMapping: 'paint-order-v1', layerCount: packet.layerCount, layerSpacing: this.layerSpacing };
    const groups = new Map<number, THREE.Group>();
    for (const data of packet.meshes) {
      const mesh = new THREE.Mesh(unpackMesh(data), this.material(data.color, data.opacity));
      this.meshPackets.set(mesh, data);
      mesh.name = `${data.primitive}-${data.sourceIndex}-${data.performedIndex}-${data.instanceIndex}-${data.role}`;
      mesh.userData = { sourceIndex: data.sourceIndex, performedIndex: data.performedIndex, instanceIndex: data.instanceIndex,
        primitive: data.primitive, role: data.role, relatedSourceIndex: data.relatedSourceIndex,
        layerIndex: data.layerIndex, layerZ: data.layerZ };
      mesh.position.z = data.layerZ;
      let group = groups.get(data.sourceIndex);
      if (!group) { group = new THREE.Group(); group.name = `instruction-${data.sourceIndex}`; groups.set(data.sourceIndex, group); this.model.add(group); }
      group.add(mesh);
    }
    this.scene.add(this.model);
    this.sceneExtent = Math.max(...packet.canvas, new THREE.Box3().setFromObject(this.model).getSize(new THREE.Vector3()).length() || 1);
    this.grid = new THREE.GridHelper(this.sceneExtent * 1.2, 20, 0x888888, 0xb0b0b0);
    this.grid.rotation.x = Math.PI / 2;
    this.grid.visible = false; this.axes.visible = false;
    this.support = new THREE.Mesh(new THREE.PlaneGeometry(...packet.canvas), new THREE.MeshStandardMaterial({
      color: packet.background, roughness: 1, side: THREE.DoubleSide,
    }));
    this.support.name = 'Canvas support';
    this.support.visible = false;
    this.scene.add(this.grid, this.axes, this.support, this.selection);
    this.selection.visible = false;
    this.placeSupport();
    this.resize = new ResizeObserver(() => this.resizeView());
    this.resize.observe(host);
    canvas.addEventListener('pointerdown', e => { this.startPointer = [e.clientX, e.clientY]; canvas.focus({ preventScroll: true }); }, { signal: this.events.signal });
    canvas.addEventListener('pointerup', e => {
      if (this.startPointer && Math.hypot(e.clientX - this.startPointer[0], e.clientY - this.startPointer[1]) < 4 && e.button === 0) this.pick(e);
      this.startPointer = null;
    }, { signal: this.events.signal });
    canvas.addEventListener('dblclick', () => this.focus(), { signal: this.events.signal });
    canvas.addEventListener('keydown', this.keyboard, { signal: this.events.signal });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { cancelAnimationFrame(this.frame); this.frame = 0; }
      else this.requestDraw();
    }, { signal: this.events.signal });
    this.resizeView(); this.match2D();
  }

  private material(color: string | number | THREE.Color, opacity: number): THREE.Material {
    const options = { color, opacity, transparent: opacity < 1, depthWrite: opacity >= 1, wireframe: this.wire, side: THREE.FrontSide };
    return this.flat ? new THREE.MeshBasicMaterial(options) : new THREE.MeshStandardMaterial({ ...options, metalness: 0, roughness: 0.7 });
  }

  async prepareAppearance() {
    const painted = this.packet.meshes.filter(packet => packet.appearance).length;
    const maxSide = Math.min(1024, Math.floor(Math.sqrt(16 * 1024 * 1024 / Math.max(1, painted))));
    await Promise.all([...this.meshPackets].map(async ([mesh, packet]) => {
      const old = mesh.material as THREE.Material;
      const resource = await prepareCircleAppearance(mesh, packet, this.packet.canvas, maxSide);
      if (resource) {
        old.dispose();
        if (this.disposed) resource.dispose(); else this.appearances.set(mesh, resource);
      }
    }));
    if (!this.disposed) { this.placeSupport(); this.requestDraw(); }
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
    if (this.controls.autoRotate) this.controls.update(Math.min(0.05, (time - this.lastTime) / 1000 || 0));
    this.lastTime = time;
    this.renderer.render(this.scene, this.camera);
    if (this.controls.autoRotate) this.requestDraw();
  };

  private rememberNow = () => { if (!this.disposed) this.changed(this.state()); };
  state(): ViewState { return { position: this.camera.position.toArray(), target: this.controls.target.toArray(), zoom: this.camera.zoom, projection: this.projection, depth: this.depth,
    layerSpacing: this.layerSpacing, background: this.background, referenceHeight: this.referenceHeight, displayZoom: this.displayZoom(),
    orthoHeight: this.camera instanceof THREE.OrthographicCamera ? this.camera.top - this.camera.bottom : 2 }; }

  restore(state: ViewState) {
    this.setProjection(state.projection); this.setDepth(state.depth); this.setLayerSpacing(state.layerSpacing ?? 1);
    this.setBackground(state.background ?? 'none'); this.referenceHeight = state.referenceHeight ?? this.referenceHeight;
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
    this.camera.position.copy(this.controls.target).add(new THREE.Vector3(...directions[name]));
    this.fit();
  }

  match2D() {
    this.setProjection('orthographic');
    const view = frontView(this.packet.canvas, this.host.clientWidth, this.host.clientHeight, this.initialView);
    this.referenceHeight = view.referenceHeight;
    const camera = this.camera as THREE.OrthographicCamera;
    camera.top = view.height / 2; camera.bottom = -view.height / 2; camera.zoom = 1;
    this.controls.target.fromArray(view.target);
    camera.position.copy(this.controls.target).add(new THREE.Vector3(0, 0, this.sceneExtent * 4 + 1));
    camera.up.set(0, 1, 0); this.resizeView(); this.controls.update(); this.controlChanged();
  }
  reset() { this.controls.autoRotate = false; this.setDepth(1); this.setLayerSpacing(1); this.match2D(); }
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
    this.scene.background = this.backgroundTexture;
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
    this.model.traverse(object => { if (object instanceof THREE.Mesh) object.scale.z = this.depth; });
    this.placeSupport(); if (this.selected) this.selection.setFromObject(this.selected); this.controlChanged();
  }
  setLayerSpacing(spacing: number) {
    this.layerSpacing = Math.max(0, Math.min(3, spacing));
    this.model.userData.layerSpacing = this.layerSpacing;
    this.model.traverse(object => { if (object instanceof THREE.Mesh) object.position.z = object.userData.layerZ * this.layerSpacing; });
    this.placeSupport(); if (this.selected) this.selection.setFromObject(this.selected); this.controlChanged();
  }
  private placeSupport() {
    const box = new THREE.Box3().setFromObject(this.model);
    const z = (box.isEmpty() ? 0 : box.min.z) - 0.02;
    this.support.position.z = z; this.grid.position.z = z - 0.001; this.axes.position.z = z;
  }

  setOption(option: string, checked: boolean) {
    if (option === 'grid') this.grid.visible = checked;
    if (option === 'axes') this.axes.visible = checked;
    if (option === 'spin') this.controls.autoRotate = checked;
    if (option === 'wire' || option === 'unlit') {
      if (option === 'wire') this.wire = checked; else this.flat = checked;
      this.model.traverse(object => {
        if (object instanceof THREE.Mesh) {
          const old = object.material as THREE.MeshStandardMaterial;
          const appearance = this.appearances.get(object);
          object.material = appearance ? new THREE.MeshBasicMaterial({ map: appearance.texture, color: 0xffffff, opacity: 1,
            transparent: true, alphaTest: 1 / 255, side: THREE.FrontSide, toneMapped: false, wireframe: this.wire })
            : this.material(old.color, old.opacity);
          old.dispose();
        }
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
    this.renderer.render(this.scene, this.camera);
    return new Promise((resolve, reject) => this.renderer.domElement.toBlob(blob => blob ? resolve(blob) : reject(new Error('empty_png')), 'image/png'));
  }
  async glb(): Promise<Blob> {
    // Geometry, current depth, source IDs and color/opacity; guides and selection stay in the viewer.
    const group = new THREE.Group(); group.add(this.model.clone(true));
    if (this.support.visible) group.add(this.support.clone());
    const bytes = await new GLTFExporter().parseAsync(group, { binary: true, onlyVisible: true });
    if (!(bytes instanceof ArrayBuffer)) throw new Error('invalid_glb');
    return new Blob([bytes], { type: 'model/gltf-binary' });
  }

  dispose() {
    if (this.disposed) return;
    this.changed(this.state()); this.disposed = true;
    cancelAnimationFrame(this.frame); clearTimeout(this.stateTimer);
    this.events.abort(); this.resize.disconnect(); this.controls.removeEventListener('change', this.controlChanged); this.controls.removeEventListener('end', this.rememberNow); this.controls.dispose();
    const geometries = new Set<THREE.BufferGeometry>(), materials = new Set<THREE.Material>();
    this.scene.traverse(object => {
      const drawable = object as THREE.Mesh;
      if (drawable.geometry) geometries.add(drawable.geometry);
      if (drawable.material) (Array.isArray(drawable.material) ? drawable.material : [drawable.material]).forEach(m => materials.add(m));
    });
    geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); this.scene.clear();
    this.backgroundTexture?.dispose();
    this.appearances.forEach(resource => resource.dispose()); this.appearances.clear();
    this.meshPackets.clear();
    this.renderer.renderLists.dispose(); this.renderer.dispose(); this.renderer.forceContextLoss(); this.renderer.domElement.remove();
  }
}
