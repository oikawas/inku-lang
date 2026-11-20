import * as THREE from 'three';
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { decay, releaseVelocity, snapsToFront, stopped, type Sample, type Velocity } from './motion';

const DEG = Math.PI / 180;
const ease = (t: number) => t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t);
interface Tween { from: THREE.Vector3; to: THREE.Vector3; start: number; length: number; then?: () => void }

/** The turning both views share: the release keeps turning (without friction
 * until touched), presets turn smoothly, and a stop near the front settles
 * onto it. Any chosen direction ends the inertia. */
export class OrbitMotion {
  dragging = false;
  /** When the view last moved, for the drawing resolution. */
  moving = 0;
  private samples: Sample[] = [];
  private inertia: Velocity | null = null;
  private tween: Tween | null = null;
  private halted = false;

  constructor(private controls: OrbitControls, private camera: () => THREE.Camera, private hooks: {
    frictionless: () => boolean; changed: () => void; requestDraw: () => void; started?: () => void;
  }) {
    controls.addEventListener('start', this.onStart);
    controls.addEventListener('end', this.onEnd);
    controls.addEventListener('change', this.onChange);
  }

  /** A touch on the view: stops any motion. True when it stopped something, so
   * the same tap does not also select. */
  touch(): boolean {
    this.halted = !!(this.inertia || this.tween);
    this.stop(); return this.halted;
  }
  /** Whether the last touch only stopped the motion. */
  get haltedByTouch() { return this.halted; }
  get active() { return !!(this.inertia || this.tween); }
  /** Whether the automatic rotation is turning the view. */
  get spinning() { return this.steady && !!this.inertia; }
  stop() { this.inertia = null; this.tween = null; this.steady = false; }
  /** A steady turn, as the automatic rotation gives (radians per second);
   * friction does not slow it, and a touch ends it like any turning. */
  spin(speed: number) { this.tween = null; this.inertia = speed ? { az: speed, po: 0 } : null; this.steady = !!speed; this.hooks.requestDraw(); }
  private steady = false;

  turnTo(direction: THREE.Vector3, length: number, then?: () => void) {
    const camera = this.camera(), offset = camera.position.clone().sub(this.controls.target);
    this.inertia = null; this.steady = false;
    this.tween = { from: offset, to: direction.clone().normalize().multiplyScalar(offset.length()), start: performance.now(), length, then };
    this.hooks.requestDraw();
  }
  /** One small turn and back, to show that the picture has depth. */
  swayOnce(isDisposed: () => boolean) {
    setTimeout(() => {
      if (isDisposed() || this.dragging || this.active) return;
      const offset = this.camera().position.clone().sub(this.controls.target);
      const turned = offset.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), 6 * DEG);
      this.tween = { from: offset.clone(), to: turned, start: performance.now(), length: 800,
        then: () => { this.tween = { from: turned, to: offset, start: performance.now(), length: 800 }; } };
      this.hooks.requestDraw();
    }, 300);
  }

  /** Advance one frame. True while anything is still moving. */
  step(dt: number): boolean {
    let animating = false;
    const camera = this.camera();
    if (this.inertia) {
      // The vertical part ends where the orbit reaches the top or bottom.
      const { az, po } = this.inertia, polar = this.controls.getPolarAngle(), frictionless = this.hooks.frictionless();
      this.controls.rotateLeft(-az * dt); this.controls.rotateUp(-po * dt); this.controls.update();
      const stuck = po !== 0 && Math.abs(this.controls.getPolarAngle() - polar) < Math.abs(po * dt) * 0.5;
      const k = this.steady ? 1 : decay(dt, frictionless);
      this.inertia = { az: az * k, po: stuck ? 0 : po * k };
      if (!this.steady && stopped(this.inertia, frictionless)) { this.inertia = null; this.snapFront(); this.hooks.changed(); }
      animating = true; this.moving = performance.now();
    }
    if (this.tween) {
      const k = Math.min(1, (performance.now() - this.tween.start) / this.tween.length);
      const { from, to } = this.tween;
      const q = new THREE.Quaternion().setFromUnitVectors(from.clone().normalize(), to.clone().normalize());
      const partial = new THREE.Quaternion().slerp(q, ease(k));
      const length = from.length() + (to.length() - from.length()) * ease(k);
      camera.position.copy(this.controls.target).add(from.clone().normalize().applyQuaternion(partial).multiplyScalar(length));
      camera.lookAt(this.controls.target); this.controls.update();
      if (k >= 1) { const then = this.tween.then; this.tween = null; then?.(); this.hooks.changed(); }
      animating = true; this.moving = performance.now();
    }
    return animating;
  }

  private snapFront() {
    const offset = this.camera().position.clone().sub(this.controls.target);
    if (snapsToFront(offset.angleTo(new THREE.Vector3(0, 0, 1)))) {
      this.tween = { from: offset, to: new THREE.Vector3(0, 0, offset.length()), start: performance.now(), length: 250 };
    }
  }
  private onStart = () => { this.dragging = true; this.samples = []; this.stop(); this.hooks.started?.(); };
  private onEnd = () => {
    this.dragging = false;
    this.inertia = releaseVelocity(this.samples, performance.now());
    if (!this.inertia) this.snapFront();
    this.hooks.changed(); this.hooks.requestDraw();
  };
  private onChange = () => {
    if (this.dragging) this.samples.push({ t: performance.now(), az: this.controls.getAzimuthalAngle(), po: this.controls.getPolarAngle() });
    this.moving = performance.now();
    this.hooks.requestDraw();
  };
  dispose() {
    this.controls.removeEventListener('start', this.onStart);
    this.controls.removeEventListener('end', this.onEnd);
    this.controls.removeEventListener('change', this.onChange);
  }
}
