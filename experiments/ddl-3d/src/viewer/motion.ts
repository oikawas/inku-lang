/** The turning that both 3D views share, as plain numbers (radians, seconds). */

const DEG = Math.PI / 180;
export const MOTION = {
  /** Release speed is read over the last 0.1 seconds of the drag. */ window: 100,
  /** Slower than this (degrees per second) the release stays still. */ minSpeed: 20,
  /** Faster releases are capped here (degrees per second). */ maxSpeed: 180,
  /** With friction, the speed falls by e every 0.5 s (half every 0.35 s). */ timeConstant: 0.5,
  /** With friction, motion ends below this speed (degrees per second). */ stopSpeed: 1.5,
  /** Within this angle of the front, a stop settles onto the front. */ snap: 3,
} as const;

export interface Sample { t: number; az: number; po: number }
export interface Velocity { az: number; po: number }

/** The shortest signed turn from one angle to another. OrbitControls keeps
 * the azimuth within ±π, so a drag across the back would otherwise read as
 * a full turn the other way. */
export function turnBetween(from: number, to: number): number {
  const d = to - from;
  return Math.atan2(Math.sin(d), Math.cos(d));
}

/** The speed the drag had when it was let go, or null when it should stay still. */
export function releaseVelocity(samples: Sample[], now: number): Velocity | null {
  const recent = samples.filter(s => now - s.t <= MOTION.window);
  if (recent.length < 2) return null;
  const a = recent[0], b = recent[recent.length - 1], dt = Math.max(1e-3, (b.t - a.t) / 1000);
  // Sum the steps, so a drag across the back keeps its own direction.
  let az = 0, po = 0;
  for (let i = 1; i < recent.length; i++) { az += turnBetween(recent[i - 1].az, recent[i].az); po += recent[i].po - recent[i - 1].po; }
  az /= dt; po /= dt;
  const speed = Math.hypot(az, po) / DEG;
  if (speed < MOTION.minSpeed) return null;
  const cap = Math.min(1, MOTION.maxSpeed / speed);
  return { az: az * cap, po: po * cap };
}

/** How much speed is left after dt seconds. */
export function decay(dt: number, frictionless: boolean): number {
  return frictionless ? 1 : Math.exp(-dt / MOTION.timeConstant);
}

/** Whether the turning has died away. Without friction it only ends on a touch. */
export function stopped(v: Velocity, frictionless: boolean): boolean {
  return Math.hypot(v.az, v.po) / DEG < (frictionless ? 1e-6 : MOTION.stopSpeed);
}

/** Whether a view this far from the front (radians) settles onto it. */
export function snapsToFront(angle: number): boolean {
  return angle > 1e-4 && angle < MOTION.snap * DEG;
}

/** The drawing resolution while the view moves. Heavy frames (over 22 ms on
 * average) lower it to 0.75 and then 0.6. Light frames (under 14 ms) raise it
 * a step again, since a turn without friction never stops. A raise that was
 * heavy at once bars that step for 5 seconds. Still, it is always 1. */
export interface Resolution { value: number; raisedAt: number; barredUntil: number }
export const FULL_RESOLUTION: Resolution = { value: 1, raisedAt: -Infinity, barredUntil: -Infinity };
export function adaptResolution(r: Resolution, averageMs: number | null, moving: boolean, now: number): Resolution {
  if (!moving) return r.value === 1 ? r : { ...FULL_RESOLUTION };
  if (averageMs === null) return r;
  if (averageMs > 22 && r.value > 0.6) {
    const barredUntil = now - r.raisedAt < 1000 ? now + 5000 : r.barredUntil;
    return { value: r.value > 0.75 ? 0.75 : 0.6, raisedAt: r.raisedAt, barredUntil };
  }
  if (averageMs < 14 && r.value < 1 && now >= r.barredUntil) return { value: r.value < 0.75 ? 0.75 : 1, raisedAt: now, barredUntil: r.barredUntil };
  return r;
}

/** How far the solids have unfolded at this angle from the front (radians).
 * At the front every solid lies flat on its layer, so the picture overlaps as
 * in 2D; thickness rises over 2-12 degrees and the layers open, up to 1.6
 * times, over 3-30 degrees. */
export function solidsFold(angle: number, open: boolean): { inflate: number; open: number } {
  return { inflate: frontWeight(angle, 2, 12), open: open ? 1 + 0.6 * frontWeight(angle, 3, 30) : 1 };
}

/** 0 at the front, 1 once turned by `to` degrees; smooth in between. */
export function frontWeight(angle: number, from: number, to: number): number {
  const t = Math.min(1, Math.max(0, (angle - from * DEG) / ((to - from) * DEG)));
  return t * t * (3 - 2 * t);
}
