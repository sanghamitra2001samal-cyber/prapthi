import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { Line2 } from 'three/examples/jsm/lines/Line2.js';
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { voiceAudio } from '../lib/voiceAudio';

/* ------------------------------------------------------------------ */
/*  ThreeHero — an audio-reactive AI "voice presence".                 */
/*                                                                    */
/*  A stylized crystal-glass AI head sits at the centre of a          */
/*  futuristic laboratory: its mouth opens with the live voice        */
/*  volume, its eyes blink, and it breathes while idle. Around it,    */
/*  concentric holographic sound-wave rings pulse to the audio        */
/*  spectrum and a cloud of ~7,000 glowing particles expands and      */
/*  vibrates with the voice. Everything is driven by the shared       */
/*  Web-Audio AnalyserNode (voiceAudio) → three.js loop, finished     */
/*  with HDRI reflections, volumetric fog, and UnrealBloom.           */
/* ------------------------------------------------------------------ */
export default function ThreeHero({ className = '' }: { className?: string }) {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const lowPower = Math.min(window.innerWidth, window.innerHeight) < 640;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    } catch {
      return;
    }
    const W = () => mount.clientWidth || window.innerWidth;
    const H = () => mount.clientHeight || window.innerHeight;

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W(), H());
    renderer.setClearColor(0x04050c, 1);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x04050c);
    scene.fog = new THREE.FogExp2(0x04050c, 0.055);

    const camera = new THREE.PerspectiveCamera(42, W() / H(), 0.1, 100);
    camera.position.set(0, 1, 8);
    camera.lookAt(0, 0.55, 0);

    const pmrem = new THREE.PMREMGenerator(renderer);
    const envRT = pmrem.fromScene(new RoomEnvironment(), 0.04);
    scene.environment = envRT.texture;

    // palette
    const CYAN = new THREE.Color(0x7ca9ff);
    const VIOLET = new THREE.Color(0x3265ff);
    const MAGENTA = new THREE.Color(0xff3ea5);
    const INDIGO = new THREE.Color(0x064eff);

    // =============== Stylized AI head ================================= //
    const head = new THREE.Group();
    head.position.set(0, 0.6, 0);
    head.scale.setScalar(0.85);
    scene.add(head);

    const skullGeo = new THREE.IcosahedronGeometry(1.15, 6);
    const skullMat = new THREE.MeshPhysicalMaterial({
      color: 0x8aa0e6,
      metalness: 0.55,
      roughness: 0.12,
      transmission: 0.62,
      thickness: 1.4,
      ior: 1.45,
      clearcoat: 1,
      clearcoatRoughness: 0.14,
      envMapIntensity: 1.5,
      emissive: 0x0a1636,
      emissiveIntensity: 0.28,
      transparent: true,
      opacity: 0.8,
    });
    const skull = new THREE.Mesh(skullGeo, skullMat);
    skull.scale.set(0.92, 1.12, 0.9);
    head.add(skull);

    // digital wireframe shell for the "AI" read
    const wire = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.19, 3),
      new THREE.MeshBasicMaterial({ color: 0x2a3ba8, wireframe: true, transparent: true, opacity: 0.22 }),
    );
    wire.scale.copy(skull.scale);
    head.add(wire);

    // eyes
    const eyeGeo = new THREE.SphereGeometry(0.1, 20, 20);
    const eyeMat = new THREE.MeshBasicMaterial({ color: 0x9ff4ff });
    const eyeL = new THREE.Mesh(eyeGeo, eyeMat);
    const eyeR = new THREE.Mesh(eyeGeo, eyeMat);
    eyeL.position.set(-0.34, 0.14, 0.92);
    eyeR.position.set(0.34, 0.14, 0.92);
    head.add(eyeL, eyeR);

    // glowing mouth bar that "opens" with audio volume (jawOpen)
    const mouthMat = new THREE.MeshBasicMaterial({ color: 0x66e0ff });
    const mouth = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.05, 0.06), mouthMat);
    mouth.position.set(0, -0.42, 0.94);
    head.add(mouth);

    // =============== Holographic sound-wave rings ==================== //
    const RING_SEG = 200;
    type Ring = { line: Line2; geo: LineGeometry; mat: LineMaterial; radius: number; tilt: number; band0: number };
    const rings: Ring[] = [];
    const ringDefs = [
      { radius: 2.0, tilt: 0.0, band0: 0 },
      { radius: 2.55, tilt: 0.35, band0: 8 },
      { radius: 3.1, tilt: -0.3, band0: 16 },
    ];
    const ringGroup = new THREE.Group();
    ringGroup.position.copy(head.position);
    scene.add(ringGroup);
    for (const def of ringDefs) {
      const pos = new Float32Array((RING_SEG + 1) * 3);
      const col = new Float32Array((RING_SEG + 1) * 3);
      const tmp = new THREE.Color();
      for (let i = 0; i <= RING_SEG; i++) {
        const a = (i / RING_SEG) * Math.PI * 2;
        pos[i * 3] = Math.cos(a) * def.radius;
        pos[i * 3 + 1] = Math.sin(a) * def.radius;
        pos[i * 3 + 2] = 0;
        tmp.copy(CYAN).lerp(VIOLET, (Math.sin(a) + 1) / 2).lerp(MAGENTA, (Math.cos(a * 2) + 1) / 4);
        col[i * 3] = tmp.r; col[i * 3 + 1] = tmp.g; col[i * 3 + 2] = tmp.b;
      }
      const geo = new LineGeometry();
      geo.setPositions(Array.from(pos));
      geo.setColors(Array.from(col));
      const mat = new LineMaterial({ vertexColors: true, linewidth: 2.4, transparent: true, opacity: 0.9 });
      mat.resolution.set(W(), H());
      const line = new Line2(geo, mat);
      line.rotation.x = def.tilt;
      ringGroup.add(line);
      rings.push({ line, geo, mat, radius: def.radius, tilt: def.tilt, band0: def.band0 });
    }

    // =============== Voice-cloud particles ========================== //
    const PN = lowPower ? 2600 : 7000;
    const pPos = new Float32Array(PN * 3);
    const pHome = new Float32Array(PN * 3);
    const pRnd = new Float32Array(PN);
    const pCol = new Float32Array(PN * 3);
    const tmpC = new THREE.Color();
    for (let i = 0; i < PN; i++) {
      // distribute in a spherical shell around the head
      const u = Math.random(), v = Math.random();
      const th = Math.acos(2 * u - 1), ph = 2 * Math.PI * v;
      const r = 2.2 + Math.random() * 2.8;
      const x = Math.sin(th) * Math.cos(ph) * r;
      const y = 0.55 + Math.cos(th) * r * 0.72;
      const z = Math.sin(th) * Math.sin(ph) * r;
      pHome[i * 3] = x; pHome[i * 3 + 1] = y; pHome[i * 3 + 2] = z;
      pPos[i * 3] = x; pPos[i * 3 + 1] = y; pPos[i * 3 + 2] = z;
      pRnd[i] = Math.random();
      tmpC.copy(INDIGO).lerp(CYAN, Math.random() * 0.6).lerp(MAGENTA, Math.random() * 0.25);
      pCol[i * 3] = tmpC.r; pCol[i * 3 + 1] = tmpC.g; pCol[i * 3 + 2] = tmpC.b;
    }
    const partGeo = new THREE.BufferGeometry();
    partGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    partGeo.setAttribute('color', new THREE.BufferAttribute(pCol, 3));
    const partMat = new THREE.PointsMaterial({
      size: 0.03,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const particles = new THREE.Points(partGeo, partMat);
    scene.add(particles);

    // reflective floor + faint reflection of the head glow
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(80, 80),
      new THREE.MeshStandardMaterial({ color: 0x03040a, metalness: 1, roughness: 0.32, envMapIntensity: 0.6 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -2.4;
    scene.add(floor);

    // =============== Lighting ======================================= //
    scene.add(new THREE.AmbientLight(0x223046, 0.7));
    const key = new THREE.PointLight(0x7ca9ff, 60, 40);
    const fill = new THREE.PointLight(0x3265ff, 48, 40);
    const rim = new THREE.PointLight(0xff3ea5, 42, 40);
    scene.add(key, fill, rim);

    // =============== Post-processing ================================ //
    const composer = new EffectComposer(renderer);
    composer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    composer.setSize(W(), H());
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(W(), H()), 0.75, 0.6, 0.68);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());

    // =============== Interaction ==================================== //
    let mx = 0, my = 0;
    const onMove = (e: PointerEvent) => {
      mx = e.clientX / window.innerWidth - 0.5;
      my = e.clientY / window.innerHeight - 0.5;
    };
    window.addEventListener('pointermove', onMove, { passive: true });

    // idle blink scheduling
    let nextBlink = 1.5, blinkT = -1;
    const BANDS = 32;
    const bands = new Float32Array(BANDS);
    const ringPos = new Float32Array((RING_SEG + 1) * 3);

    const clock = new THREE.Clock();
    let raf = 0;
    const render = () => {
      const t = clock.getElapsedTime();
      const level = voiceAudio.getLevel();
      const speaking = voiceAudio.speaking;
      voiceAudio.getBands(BANDS, bands);

      // ---- head idle + speaking ---- //
      head.rotation.y = Math.sin(t * 0.5) * 0.12 + mx * 0.5;
      head.rotation.x = Math.sin(t * 0.4) * 0.05 + my * 0.25;
      const breathe = 1 + Math.sin(t * 1.1) * 0.02 + level * 0.05;
      skull.scale.set(0.92 * breathe, 1.12 * breathe, 0.9 * breathe);
      wire.rotation.y = t * 0.15;

      // mouth opens with volume, with a little randomness (not robotic)
      const open = 0.05 + level * (0.9 + Math.sin(t * 40) * 0.12);
      mouth.scale.y = 1 + open * 9;
      mouth.scale.x = 1 - open * 0.25;
      (mouth.material as THREE.MeshBasicMaterial).color
        .copy(CYAN).lerp(MAGENTA, Math.min(1, level * 1.4));

      // blink
      if (blinkT < 0 && t > nextBlink) { blinkT = t; nextBlink = t + 2 + Math.random() * 4; }
      let eyeY = 1;
      if (blinkT >= 0) {
        const p = (t - blinkT) / 0.14;
        eyeY = p >= 1 ? 1 : Math.abs(Math.cos(p * Math.PI));
        if (p >= 1) blinkT = -1;
      }
      eyeL.scale.y = eyeY; eyeR.scale.y = eyeY;
      const eyeGlow = speaking ? 1.6 : 1;
      (eyeMat.color as THREE.Color).copy(CYAN).multiplyScalar(eyeGlow);

      // ---- holographic rings ---- //
      ringGroup.rotation.z = t * 0.08;
      for (const ring of rings) {
        for (let i = 0; i <= RING_SEG; i++) {
          const a = (i / RING_SEG) * Math.PI * 2;
          const bi = (ring.band0 + i) % BANDS;
          const amp = speaking ? bands[bi] * 0.9 : 0;
          const idle = Math.sin(a * 5 + t * 2) * 0.03;
          const r = ring.radius + idle + amp;
          ringPos[i * 3] = Math.cos(a) * r;
          ringPos[i * 3 + 1] = Math.sin(a) * r;
          ringPos[i * 3 + 2] = 0;
        }
        ring.geo.setPositions(Array.from(ringPos));
        ring.mat.opacity = 0.55 + (speaking ? 0.4 : 0);
      }

      // ---- particle voice cloud ---- //
      const expand = 1 + level * 0.55;
      for (let i = 0; i < PN; i++) {
        const hx = pHome[i * 3], hy = pHome[i * 3 + 1], hz = pHome[i * 3 + 2];
        const bi = (i * 7) % BANDS;
        const vib = speaking ? bands[bi] * 0.25 : 0;
        const fl = Math.sin(t * (0.4 + pRnd[i] * 0.8) + i) * 0.04;
        pPos[i * 3] = hx * expand + Math.sin(t * 3 + i) * vib;
        pPos[i * 3 + 1] = hy * (1 + (expand - 1) * 0.6) + fl + Math.cos(t * 3.3 + i) * vib;
        pPos[i * 3 + 2] = hz * expand + Math.cos(t * 3 + i) * vib;
      }
      partGeo.attributes.position.needsUpdate = true;
      partMat.opacity = 0.55 + level * 0.4;
      partMat.size = 0.028 + level * 0.02;
      particles.rotation.y = t * 0.04;

      // ---- lights ---- //
      key.position.set(Math.cos(t * 0.5) * 5, 3.5, 4);
      fill.position.set(-4.5, 1.5 + Math.sin(t * 0.4) * 1.2, 3);
      rim.position.set(Math.sin(t * 0.6) * 4, 1, -3.5);

      // ---- slow cinematic camera orbit + parallax ---- //
      const cx = Math.sin(t * 0.12) * 1.1 + mx * 1.0;
      const cy = 1 - my * 0.6 + Math.sin(t * 0.2) * 0.15;
      camera.position.x += (cx - camera.position.x) * 0.04;
      camera.position.y += (cy - camera.position.y) * 0.04;
      camera.lookAt(0, 0.55, 0);

      composer.render();
      raf = requestAnimationFrame(render);
    };
    render();
    if (reduced) cancelAnimationFrame(raf);

    const onResize = () => {
      const w = W(), h = H();
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h);
      rings.forEach((r) => r.mat.resolution.set(w, h));
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('resize', onResize);
      skullGeo.dispose(); skullMat.dispose();
      wire.geometry.dispose(); (wire.material as THREE.Material).dispose();
      eyeGeo.dispose(); eyeMat.dispose();
      mouth.geometry.dispose(); mouthMat.dispose();
      rings.forEach((r) => { r.geo.dispose(); r.mat.dispose(); });
      partGeo.dispose(); partMat.dispose();
      floor.geometry.dispose(); (floor.material as THREE.Material).dispose();
      bloom.dispose(); composer.dispose();
      envRT.dispose(); pmrem.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
  }, []);

  return <div ref={mountRef} className={className} aria-hidden />;
}
