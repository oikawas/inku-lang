import { Color, Vector2, Vector3, type MeshLambertMaterial, type Texture } from 'three';

/** Uniforms every solid shares, updated once a frame. */
export interface SolidUniforms {
  /** 0 at the front, 1 once turned: shading, the sphere's band and shadows grow with it. */
  uWeight: { value: number };
  /** The light that shades the faces (unit, world); it follows the pointer. */
  uR: { value: Vector3 };
  /** The paper's hue (its colour over its strongest channel); darkened faces lean toward it. */
  uTone: { value: Vector3 };
  /** 0 turns the shading off (flat colour). */
  uLit: { value: number };
}

export function solidUniforms(paper: string): SolidUniforms {
  return { uWeight: { value: 0 }, uR: { value: new Vector3(-0.24, 0.24, 0.94).normalize() }, uTone: { value: paperTone(paper) }, uLit: { value: 1 } };
}

/** The paper's hue: its colour over its strongest channel. Darkened faces
 * lean a third of the way toward it, so shade is never a step toward black
 * (the author, 2026-11-16: darkening must be as paint does, not black). */
export function paperTone(paper: string): Vector3 {
  const c = new Color(paper), m = Math.max(c.r, c.g, c.b);
  return m < 0.05 ? new Vector3(1, 1, 1) : new Vector3(c.r / m, c.g / m, c.b / m);
}

/** The face factor before the tint: 1 for a face toward the paper's front,
 * however the light is set; up to 1.10 and down to 0.62 as faces turn. */
export function faceShade(normal: Vector3, light: Vector3, weight: number): number {
  const s = 1 + weight * (0.29 * (normal.dot(light) - light.z) + 0.10 * normal.y);
  return Math.min(1.10, Math.max(0.62, s));
}

const declarations = /* glsl */ `
uniform float uWeight; uniform vec3 uR; uniform vec3 uTone; uniform float uLit; uniform float uGlow;
varying vec2 vSurf;
#ifdef SOLID_PAINT
uniform sampler2D uBlur; uniform float uWallOpacity; uniform vec2 uTexel;
#endif
`;
/** After three declares `map`. */
const height = /* glsl */ `
#ifdef SOLID_PAINT
// The paint's height: mostly its coverage (much paint keeps its grain in
// alpha, one colour), a little its lightness.
float paintHeight( vec2 uv ) {
  vec4 p = texture2D( map, uv );
  return p.a * ( 1.0 + 0.5 * ( dot( p.rgb, vec3( 0.299, 0.587, 0.114 ) ) - 0.5 ) );
}
#endif
`;

/** Paint and light the solids the same way, on three's Lambert material so
 * shadows, colour space, alpha test and wireframe stay three's. `surf` is per
 * vertex: x = 1 on a wall, y = the sphere's height (-1 back .. 1 front; 2 for
 * no blend). At the front (weight 0) the colour is the 2D paint itself. */
export function shadeSolid(material: MeshLambertMaterial, shared: SolidUniforms, paint?: { blur: Texture; wallOpacity: number; texel: [number, number] }) {
  material.defines = { ...(material.defines ?? {}), ...(paint ? { SOLID_PAINT: '' } : {}) };
  material.customProgramCacheKey = () => paint ? 'inku-solid-paint' : 'inku-solid';
  material.onBeforeCompile = shader => {
    Object.assign(shader.uniforms, shared);
    shader.uniforms.uGlow = glowOf(material);
    if (paint) {
      shader.uniforms.uBlur = { value: paint.blur }; shader.uniforms.uWallOpacity = { value: paint.wallOpacity };
      shader.uniforms.uTexel = { value: new Vector2(...paint.texel) };
    }
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>\n${paint ? 'attribute vec2 surf;' : ''}\nvarying vec2 vSurf;`)
      .replace('#include <uv_vertex>', `#include <uv_vertex>\n${paint ? 'vSurf = surf;' : 'vSurf = vec2(0.0, 2.0);'}`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>\n${declarations}`)
      .replace('#include <map_pars_fragment>', `#include <map_pars_fragment>\n${height}`)
      .replace('#include <map_fragment>', /* glsl */ `
        float solidRelief = 0.0;
#ifdef SOLID_PAINT
        // Raking light raises the brush marks: the slope of the paint's height
        // toward the light, as the view turns. Where a texel spans more than two
        // screen pixels the relief fades, so coarse paint does not turn to tiles.
        if ( vSurf.x < 0.5 ) {
          vec2 g = vec2( paintHeight( vMapUv + vec2( uTexel.x, 0.0 ) ) - paintHeight( vMapUv - vec2( uTexel.x, 0.0 ) ),
                         paintHeight( vMapUv + vec2( 0.0, uTexel.y ) ) - paintHeight( vMapUv - vec2( 0.0, uTexel.y ) ) ) * 0.5;
          vec2 r = length( uR.xy ) > 1e-4 ? normalize( uR.xy ) : vec2( 0.0 );
          float pixelsPerTexel = 1.0 / max( length( fwidth( vMapUv ) / uTexel ), 1e-4 );
          solidRelief = -0.5 * dot( g, r ) * min( 1.0, 2.0 / max( pixelsPerTexel, 1e-4 ) );
        }
        // Walls take the paint's colour folded in from the edge, opaque; a sphere
        // turns from the front paint to its blurred colour toward the back.
        vec4 paint = texture2D( map, vMapUv );
        if ( vSurf.x > 0.5 ) diffuseColor *= vec4( paint.rgb, uWallOpacity );
        else {
          float k = uWeight * smoothstep( 0.75, 0.25, vSurf.y );
          vec3 blurred = texture2D( uBlur, vMapUv ).rgb;
          diffuseColor *= vec4( mix( paint.rgb, blurred, k ), mix( paint.a, 1.0, k ) );
        }
#else
        #include <map_fragment>
#endif`)
      .replace('#include <opaque_fragment>', /* glsl */ `
        {
          // One shade from the faces' turn away from the paper's front, and the
          // shadow of the one directional light; darkness takes the paper's tint.
          vec3 nW = inverseTransformDirection( normal, viewMatrix );
          float s = 1.0 + uWeight * ( 0.29 * ( dot( nW, uR ) - uR.z ) + 0.10 * nW.y + solidRelief );
          s = clamp( s, 0.62, 1.10 );
          float shadow = 1.0;
#if NUM_DIR_LIGHTS > 0
          shadow = directLight.color.r / max( directionalLights[ 0 ].color.r, 1e-4 );
#endif
          float shade = mix( 1.0, s * shadow, uLit );
          float dark = clamp( ( 1.0 - shade ) / 0.38, 0.0, 1.0 );
          outgoingLight = diffuseColor.rgb * shade * mix( vec3( 1.0 ), uTone, 0.35 * dark );
          // A picked solid glows for a moment, lifting toward white.
          outgoingLight = mix( outgoingLight, vec3( 1.0 ), 0.45 * uGlow );
        }
        #include <opaque_fragment>`);
  };
  material.needsUpdate = true;
}

/** The picked solid's glow, 0..1, read by its material's shader. */
export function glowOf(material: { userData: Record<string, unknown> }): { value: number } {
  return (material.userData.glow ??= { value: 0 }) as { value: number };
}
