/** The glass block: each pixel follows its light path through the glass.
 * Colours stay in display (sRGB) values, as the 2D painter composites. */

export const MAX_SLOTS = 9; // eight fan layers and the presence plane

export const glassVertex = /* glsl */ `
out vec3 vWorld;
void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vWorld = world.xyz;
  gl_Position = projectionMatrix * viewMatrix * world;
}`;

export const glassFragment = /* glsl */ `
precision highp float;
precision highp sampler2DArray;
#define SLOTS ${MAX_SLOTS}
in vec3 vWorld;
out vec4 outColor;

uniform sampler2DArray uLayers;
uniform float uLayerSize;
uniform int uSlots;
uniform vec4 uPlane[SLOTS];   // z = c + gx x + gy y: gx, gy, c, opacity
uniform int uPresence;        // 1 when slot 0 is the presence plane (no sheen)
uniform vec4 uRect[SLOTS];    // content rectangle in world x, y: x0, y0, x1, y1
uniform vec3 uSigma[SLOTS];   // absorption of the glass in front of slot k (between k and k+1)
uniform float uPulse[SLOTS];
uniform vec4 uBox[6];         // outward normal, offset: dot(n, p) <= d inside
uniform vec3 uSigmaAll;       // absorption of the whole block, for one colour
uniform bool uOrtho;
uniform vec3 uViewDir;
uniform float uPixelWorld;
uniform float uWeight;        // front weight: 0 at the front view
uniform float uLeaf;
uniform bool uBluish;
uniform vec3 uBg;
uniform float uRoom;
uniform vec3 uLightC[3];      // centres of the lights A, B and D
uniform vec3 uLightU[3];
uniform vec3 uLightV[3];
uniform vec3 uLightSize[3];   // half width, half height, brightness
uniform float uLightLow;
uniform int uBounces;

const float IOR = 1.5;

float fresnel(float cosI) {
  float f0 = 0.04;
  return f0 + (1.0 - f0) * pow(1.0 - clamp(cosI, 0.0, 1.0), 5.0);
}

float rectLight(int k, vec3 q, vec3 d, float soft) {
  vec3 n = normalize(uLightC[k]);
  float denom = dot(d, n);
  if (denom <= 1e-4) return 0.0;
  float t = dot(uLightC[k] - q, n) / denom;
  if (t <= 0.0) return 0.0;
  vec3 h = q + d * t - uLightC[k];
  float s = soft * t + 1e-3;
  float u = smoothstep(uLightSize[k].x + s, uLightSize[k].x - s, abs(dot(h, uLightU[k])));
  float v = smoothstep(uLightSize[k].y + s, uLightSize[k].y - s, abs(dot(h, uLightV[k])));
  return u * v * uLightSize[k].z;
}

float lights(vec3 q, vec3 d, float soft) {
  float low = uLightLow * smoothstep(0.0, -0.8, d.y);
  return rectLight(0, q, d, soft) + rectLight(1, q, d, soft) + rectLight(2, q, d, soft) + low;
}

vec3 env(vec3 q, vec3 d) {
  vec3 base = mix(uBg, uBg * uRoom, smoothstep(-0.15, 0.25, d.z));
  return base + vec3(lights(q, d, 0.02));
}

// Distance to where the ray leaves the block, and the face it leaves by.
float exitBox(vec3 p, vec3 d, out int face) {
  float best = 1e9; face = 0;
  for (int i = 0; i < 6; i++) {
    float dn = dot(uBox[i].xyz, d);
    if (dn > 1e-6) {
      float t = (uBox[i].w - dot(uBox[i].xyz, p)) / dn;
      if (t < best) { best = t; face = i; }
    }
  }
  return max(best, 0.0);
}

vec3 planeNormal(int k) { return normalize(vec3(-uPlane[k].x, -uPlane[k].y, 1.0)); }
float planeZ(int k, vec2 xy) { return uPlane[k].z + uPlane[k].x * xy.x + uPlane[k].y * xy.y; }

// Hit of a layer plane z = c + gx x + gy y.
float hitPlane(int k, vec3 p, vec3 d) {
  vec3 n = vec3(-uPlane[k].x, -uPlane[k].y, 1.0);   // n.p = c on the plane
  float dn = dot(n, d);
  if (abs(dn) < 1e-7) return -1.0;
  return (uPlane[k].z - dot(n, p)) / dn;
}

vec4 sampleLayer(int k, vec3 h, vec3 d) {
  vec4 r = uRect[k];
  vec2 uv = vec2((h.x - r.x) / (r.z - r.x), (h.y - r.y) / (r.w - r.y));
  if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) return vec4(0.0);
  float texel = max((r.z - r.x), (r.w - r.y)) / uLayerSize;
  float slant = 1.0 / max(abs(dot(d, planeNormal(k))), 0.05);
  float lod = log2(max(uPixelWorld * sqrt(slant) / texel, 1e-4));
  return textureLod(uLayers, vec3(uv.x, 1.0 - uv.y, float(k)), max(lod, 0.0));
}

// Light the leaf at h catches: reflect inside the glass, leave the block if
// the glass lets it, and see whether it meets a light.
float leafLight(int k, vec3 h, vec3 d) {
  vec3 n = planeNormal(k);
  if (dot(n, d) > 0.0) n = -n;
  vec3 r = reflect(d, n);
  int face;
  float t = exitBox(h, r, face);
  vec3 q = h + r * t;
  vec3 out_n = uBox[face].xyz;
  vec3 o = refract(r, -out_n, IOR);
  if (dot(o, o) < 1e-6) return 0.0;  // total internal reflection
  return lights(q, normalize(o), 0.22 * 0.6);
}

vec3 leafColor(vec3 c) {
  float m = max(c.r, max(c.g, c.b));
  float sat = (m - min(c.r, min(c.g, c.b))) / max(m, 0.05);
  vec3 silver = uBluish ? vec3(0.90, 0.95, 1.0) : vec3(1.0);
  return mix(silver, c / max(m, 0.05), smoothstep(0.08, 0.35, sat));
}

// Layer colours: the glass takes the colour of the nearest layer behind the
// point, where some layer is still in front of it (the glass in front of the
// front layer stays clear, as before). Planes may cross away from the paint.
vec3 sigmaAt(vec3 p) {
  vec3 s = uSigmaAll;
  float best = -1e9; int below = -1; bool above = false;
  for (int k = 0; k < SLOTS; k++) {
    if (k >= uSlots) break;
    float z = planeZ(k, p.xy);
    if (z < p.z) { if (z > best) { best = z; below = k; } } else above = true;
  }
  if (below >= 0 && above) for (int k = 0; k < SLOTS; k++) if (k == below) s += uSigma[k];
  return s;
}

void main() {
  vec3 d = uOrtho ? normalize(uViewDir) : normalize(vWorld - cameraPosition);
  vec3 p = vWorld;
  // Entry face: the face the point lies on.
  int face = 0; float near = 1e9;
  for (int i = 0; i < 6; i++) {
    float e = abs(dot(uBox[i].xyz, p) - uBox[i].w);
    if (e < near) { near = e; face = i; }
  }
  vec3 n = uBox[face].xyz;
  float cosI = max(-dot(d, n), 0.0);
  float F = fresnel(cosI) * uWeight;
  vec3 color = F * env(p, reflect(d, n));
  float thr = 1.0 - F;
  vec3 tint = vec3(1.0);
  d = refract(d, n, 1.0 / IOR);
  for (int bounce = 0; bounce < 8; bounce++) {
    if (bounce >= uBounces) break;
    int exitFace;
    float tExit = exitBox(p + d * 1e-5, d, exitFace) + 1e-5;
    // Hits along the path. Planes may cross where a later layer has no paint,
    // so they are laid in distance order; at the front (weight 0) in index
    // order, so the front view keeps the 2D overlap exactly.
    float hits[SLOTS]; float keys[SLOTS]; int order[SLOTS]; int count = 0;
    bool forward = d.z > 0.0;
    for (int k = 0; k < SLOTS; k++) {
      hits[k] = -1.0;
      if (k >= uSlots) continue;
      float t = hitPlane(k, p, d);
      if (!(t > 1e-5 && t < tExit)) continue;
      hits[k] = t;
      // Equal distances: a path going in meets the later layer first.
      float rank = forward ? float(k) : float(SLOTS - k);
      float key = uWeight <= 0.0 ? rank : t + rank * 1e-6;
      int at = count;
      for (int j = SLOTS - 1; j > 0; j--) {
        if (j > count) continue;
        if (keys[j - 1] > key) { keys[j] = keys[j - 1]; order[j] = order[j - 1]; at = j - 1; } else break;
      }
      keys[at] = key; order[at] = k; count++;
    }
    float last = 0.0;
    for (int j = 0; j < SLOTS; j++) {
      if (j >= count) break;
      int k = order[j];
      float th = hits[k];
      vec3 h = p + d * th;
      if (th > last) {
        vec3 mid = p + d * (0.5 * (last + th));
        tint *= exp(-sigmaAt(mid) * (th - last));
        last = th;
      }
      vec4 s = sampleLayer(k, h, d) * uPlane[k].w;
      if (s.a <= 1e-4) continue;
      vec3 c = s.rgb / s.a;
      float glow = k >= uPresence ? leafLight(k, h, d) : 0.0;
      float hl = 1.0 - exp(-2.2 * (uLeaf + uPulse[k]) * glow * uWeight);
      vec3 lit = 1.0 - (1.0 - c) * (1.0 - leafColor(c) * hl);
      color += thr * tint * s.a * lit;
      thr *= 1.0 - s.a;
    }
    vec3 q = p + d * tExit;
    tint *= exp(-sigmaAt(p + d * (0.5 * (last + tExit))) * (tExit - last));
    vec3 on = uBox[exitFace].xyz;
    vec3 o = refract(d, -on, IOR);
    float R;
    if (dot(o, o) < 1e-6) R = 1.0;
    else R = fresnel(dot(normalize(o), on)) * uWeight;
    if (R < 1.0) color += thr * tint * (1.0 - R) * env(q, normalize(o));
    thr *= R;
    // Stop by the light left, fading the next image out between 12% and 6%.
    float keep = smoothstep(0.06, 0.12, thr * max(tint.r, max(tint.g, tint.b)));
    if (keep < 1.0 && thr > 0.0) { color += thr * (1.0 - keep) * tint * env(q, reflect(d, on)); thr *= keep; }
    if (thr <= 1e-4) break;
    d = reflect(d, on); p = q;
  }
  color += thr * tint * env(p, d);
  outColor = vec4(clamp(color, 0.0, 1.0), 1.0);
}`;
