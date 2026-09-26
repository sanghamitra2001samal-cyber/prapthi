import { useEffect, useRef } from 'react';
import * as THREE from 'three';

/* ------------------------------------------------------------------ */
/*  DashboardBG — a live Three.js "energy field" behind the app.       */
/*                                                                    */
/*  A fullscreen shader plane paints slow, drifting glows in the       */
/*  current theme's accent colours, with a sparse layer of floating    */
/*  particles for depth. It sits fixed behind the glass panels         */
/*  (pointer-events: none) so every control stays fully usable, reads   */
/*  the live `--color-*` tokens so it matches dark/light instantly,     */
/*  pauses when the tab is hidden or reduced-motion is set, and is      */
/*  disposed cleanly on unmount.                                       */
/* ------------------------------------------------------------------ */
function cssColor(name: string, fallback: string): THREE.Color {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return new THREE.Color(v || fallback);
  } catch {
    return new THREE.Color(fallback);
  }
}

export default function DashboardBG() {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
    } catch {
      return;
    }
    const W = () => mount.clientWidth || window.innerWidth;
    const H = () => mount.clientHeight || window.innerHeight;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setSize(W(), H());
    renderer.setClearColor(0x000000, 0);
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

    // ---- theme colour uniforms ------------------------------------- //
    const isLight = () => document.documentElement.classList.contains('theme-light');
    const uniforms = {
      uTime: { value: 0 },
      uRes: { value: new THREE.Vector2(W(), H()) },
      uBg: { value: cssColor('--color-bg', '#0b0d12') },
      uAccent: { value: cssColor('--color-accent', '#2f6bef') },
      uCyan: { value: new THREE.Color(0x3265ff) },
      uMag: { value: new THREE.Color(0x7ca9ff) },
      uGlow: { value: isLight() ? 0.16 : 0.55 },
    };
    const syncTheme = () => {
      uniforms.uBg.value = cssColor('--color-bg', '#0b0d12');
      uniforms.uAccent.value = cssColor('--color-accent', '#2f6bef');
      uniforms.uGlow.value = isLight() ? 0.16 : 0.55;
    };
    window.addEventListener('vf-theme', syncTheme);

    // ---- flowing energy-field plane -------------------------------- //
    const planeMat = new THREE.ShaderMaterial({
      uniforms,
      vertexShader: `
        varying vec2 vUv;
        void main(){ vUv = uv; gl_Position = vec4(position, 1.0); }
      `,
      fragmentShader: `
        precision highp float;
        uniform float uTime; uniform vec2 uRes;
        uniform vec3 uBg, uAccent, uCyan, uMag; uniform float uGlow;
        varying vec2 vUv;
        float glow(vec2 p, vec2 c, float s){ return exp(-length(p - c) * s); }
        void main(){
          float t = uTime;
          float aspect = uRes.x / max(uRes.y, 1.0);
          vec2 p = vUv; p.x *= aspect;
          vec2 c1 = vec2((0.16 + 0.06 * sin(t * 0.12)) * aspect, 0.20 + 0.05 * cos(t * 0.10));
          vec2 c2 = vec2((0.84 + 0.05 * sin(t * 0.09 + 1.0)) * aspect, 0.30 + 0.06 * cos(t * 0.13));
          vec2 c3 = vec2((0.58 + 0.07 * sin(t * 0.07 + 2.0)) * aspect, 0.86 + 0.05 * cos(t * 0.11));
          vec2 c4 = vec2((0.35 + 0.05 * sin(t * 0.10 + 4.0)) * aspect, 0.55 + 0.07 * sin(t * 0.06));
          vec3 col = uBg;
          col += uAccent * glow(p, c1, 2.7) * uGlow;
          col += uCyan   * glow(p, c2, 2.9) * uGlow * 0.85;
          col += uAccent * glow(p, c3, 2.6) * uGlow * 0.8;
          col += uMag    * glow(p, c4, 3.3) * uGlow * 0.5;
          gl_FragColor = vec4(col, 1.0);
        }
      `,
      depthWrite: false,
    });
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), planeMat);
    scene.add(plane);

    // ---- drifting particles ---------------------------------------- //
    const PN = Math.min(window.innerWidth, window.innerHeight) < 700 ? 220 : 520;
    const pPos = new Float32Array(PN * 3);
    const pSpd = new Float32Array(PN);
    for (let i = 0; i < PN; i++) {
      pPos[i * 3] = (Math.random() - 0.5) * 2;
      pPos[i * 3 + 1] = (Math.random() - 0.5) * 2;
      pPos[i * 3 + 2] = 0;
      pSpd[i] = 0.02 + Math.random() * 0.05;
    }
    const partGeo = new THREE.BufferGeometry();
    partGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    const partMat = new THREE.PointsMaterial({
      color: uniforms.uAccent.value.clone(),
      size: 0.006,
      transparent: true,
      opacity: 0.5,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const particles = new THREE.Points(partGeo, partMat);
    scene.add(particles);

    // ---- interaction: gentle parallax ------------------------------ //
    let mx = 0, my = 0;
    const onMove = (e: PointerEvent) => {
      mx = (e.clientX / window.innerWidth - 0.5) * 0.06;
      my = (e.clientY / window.innerHeight - 0.5) * 0.06;
    };
    window.addEventListener('pointermove', onMove, { passive: true });

    // ---- loop (throttled + pause when hidden) ---------------------- //
    const clock = new THREE.Clock();
    let raf = 0;
    let running = true;
    const render = () => {
      if (running) {
        const t = reduced ? 0 : clock.getElapsedTime();
        uniforms.uTime.value = t;
        // drift particles upward, wrap around
        for (let i = 0; i < PN; i++) {
          pPos[i * 3 + 1] += pSpd[i] * 0.01;
          pPos[i * 3] += Math.sin(t * 0.2 + i) * 0.0004;
          if (pPos[i * 3 + 1] > 1) pPos[i * 3 + 1] = -1;
        }
        partGeo.attributes.position.needsUpdate = true;
        particles.position.set(mx, my, 0);
        (partMat.color as THREE.Color).copy(uniforms.uAccent.value);
        renderer.render(scene, camera);
      }
      raf = requestAnimationFrame(render);
    };
    render();
    if (reduced) { renderer.render(scene, camera); }

    const onVis = () => { running = !document.hidden && !reduced; };
    document.addEventListener('visibilitychange', onVis);

    const onResize = () => {
      renderer.setSize(W(), H());
      uniforms.uRes.value.set(W(), H());
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('vf-theme', syncTheme);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', onVis);
      plane.geometry.dispose();
      planeMat.dispose();
      partGeo.dispose();
      partMat.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
  }, []);

  return <div ref={mountRef} className="pointer-events-none fixed inset-0 z-0 h-full w-full" aria-hidden />;
}
