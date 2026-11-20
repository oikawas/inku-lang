/** Two touch taps close in time and place. On iPhone and iPad a double tap on
 * the 3D view returns to 2D (the author, 2026-11-20), as a single tap on the
 * 2D picture opens 3D; a mouse's double click still focuses the selection. */
export class DoubleTap {
  private last: { t: number; x: number; y: number } | null = null;
  private within: number; private reach: number;
  constructor(within = 350, reach = 40) { this.within = within; this.reach = reach; }
  /** A tap ended here. True when it completes a double tap. */
  tap(t: number, x: number, y: number): boolean {
    const last = this.last;
    if (last && t - last.t <= this.within && Math.hypot(x - last.x, y - last.y) <= this.reach) { this.last = null; return true; }
    this.last = { t, x, y }; return false;
  }
  clear() { this.last = null; }
}

/** iPhone and iPad (WebKit with touch); a Mac's Safari has no touch points. */
export const appleTouch = () => navigator.vendor.startsWith('Apple') && navigator.maxTouchPoints > 0;
