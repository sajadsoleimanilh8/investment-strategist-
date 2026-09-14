/**
 * The public landing page ("/").
 *
 * A signed-in visitor never sees this — RootGate sends them straight to
 * /dashboard. This page exists to earn the click that gets a stranger to
 * /signup, so its job is different from every other page in this app: it
 * has no live data, no query, nothing to load. Everything under "Example
 * data" is illustrative on purpose (SPEC: never present invented numbers
 * as if they were the visitor's own).
 *
 * The hero is a live Three.js scene (a bitcoin-coin stack that separates on
 * scroll to reveal an emerald "financial intelligence core"), scrubbed by
 * GSAP ScrollTrigger and smoothed by Lenis. All three plus the "premium
 * polish" layer below (loader, custom cursor, magnetic buttons, card tilt,
 * scroll reveals) are imperative-DOM code kept out of React's render cycle
 * on purpose: this is exactly the kind of continuous, per-frame work that
 * fighting the render cycle would only slow down. Everything is wrapped in
 * try/catch and gated by `prefers-reduced-motion` / pointer-capability
 * checks, and every side effect it starts is torn down on unmount.
 */
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import * as THREE from "three";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";

import "../styles/landing.css";

function SplitWords({ text }: { text: string }) {
  return (
    <>
      {text.split(" ").map((word, i, arr) => (
        <span className="reveal-word" key={i}>
          {word}
          {i < arr.length - 1 ? " " : ""}
        </span>
      ))}
    </>
  );
}

const HEALTH_COMPONENTS = [
  { name: "Savings rate", target: 78, points: "15.6 / 20" },
  { name: "Emergency fund", target: 60, points: "12.0 / 20" },
  { name: "Debt load", target: 85, points: "17.0 / 20" },
  { name: "Budget stability", target: 70, points: "14.0 / 20" },
  { name: "Goal progress", target: 45, points: "9.0 / 20" },
];
const HEALTH_SCORE = 67.6; // sum of the five example components above
const DIAL_CIRCUMFERENCE = 326.7; // 2 * PI * 52 (the dial's radius, in the svg below)

const CAPABILITIES = [
  { n: "01", title: "Goals", body: "Trajectory and allocation for every goal you fund, tracked against your real progress." },
  { n: "02", title: "Simulate", body: "Run a scenario, a raise, a move, a new debt, and see the honest downstream effect." },
  { n: "03", title: "Market", body: "A restrained watchlist. Prices and context, not noise." },
  { n: "04", title: "Ask", body: "A financial assistant that explains your own numbers back to you, in plain terms." },
];

export function Landing() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const eyebrowRef = useRef<HTMLDivElement>(null);
  const statementRef = useRef<HTMLDivElement>(null);
  const progressFillRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const heroRef = useRef<HTMLElement>(null);
  const heroStageRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const loaderRef = useRef<HTMLDivElement>(null);
  const loaderMarkRef = useRef<HTMLSpanElement>(null);
  const loaderFillRef = useRef<HTMLDivElement>(null);
  const scrollProgressRef = useRef<HTMLDivElement>(null);
  const cursorDotRef = useRef<HTMLDivElement>(null);
  const cursorRingRef = useRef<HTMLDivElement>(null);
  const manifestoLedeRef = useRef<HTMLParagraphElement>(null);
  const healthRef = useRef<HTMLElement>(null);
  const dialNumRef = useRef<HTMLSpanElement>(null);
  const dialArcRef = useRef<SVGCircleElement>(null);

  // ---------------- the 3D hero scene ----------------
  useEffect(() => {
    const canvas = canvasRef.current;
    const eyebrow = eyebrowRef.current;
    const statement = statementRef.current;
    const progressFill = progressFillRef.current;
    const nav = navRef.current;
    if (!canvas || !eyebrow || !statement || !progressFill || !nav) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function easeInOutCubic(t: number) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
    function lerp(a: number, b: number, t: number) { return a + (b - a) * t; }

    let sceneReady = false;
    let renderer: THREE.WebGLRenderer | undefined;
    let scene: THREE.Scene | undefined;
    let camera: THREE.PerspectiveCamera | undefined;
    let applyProgress: ((p: number) => void) | undefined;
    let tick: (() => void) | undefined;
    let resize: (() => void) | undefined;
    let rafId = 0;
    let running = true;
    let disposed = false;
    const cleanups: Array<() => void> = [];

    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setClearColor(0x000000, 0);
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;

      scene = new THREE.Scene();
      scene.fog = new THREE.Fog(0x0a0b09, 8, 21);
      camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100);
      camera.position.set(0, 0, 14);

      // everything sits inside this rig, tilted into a three-quarter view
      const rig = new THREE.Group();
      rig.rotation.set(-0.2, 0.5, 0);
      scene.add(rig);

      scene.add(new THREE.AmbientLight(0x1c3b2e, 0.5));

      const keyLight = new THREE.DirectionalLight(0xf0c98a, 2.1);
      keyLight.position.set(6, 9, 7);
      keyLight.castShadow = true;
      keyLight.shadow.mapSize.set(1024, 1024);
      keyLight.shadow.camera.near = 1;
      keyLight.shadow.camera.far = 25;
      keyLight.shadow.camera.left = -8;
      keyLight.shadow.camera.right = 8;
      keyLight.shadow.camera.top = 8;
      keyLight.shadow.camera.bottom = -8;
      keyLight.shadow.radius = 4;
      scene.add(keyLight);

      const rimLight = new THREE.PointLight(0x2f9c70, 2.0, 50);
      rimLight.position.set(-9, -5, -7);
      scene.add(rimLight);
      const fillLight = new THREE.PointLight(0xffffff, 0.45, 40);
      fillLight.position.set(0, 3, 11);
      scene.add(fillLight);

      const ground = new THREE.Mesh(
        new THREE.CircleGeometry(9, 64),
        new THREE.MeshStandardMaterial({ color: 0x0c0d0b, metalness: 0.3, roughness: 0.35 }),
      );
      ground.rotation.x = -Math.PI / 2;
      ground.position.y = -2.4;
      ground.receiveShadow = true;
      rig.add(ground);

      const gem = new THREE.Mesh(
        new THREE.IcosahedronGeometry(0.85, 1),
        new THREE.MeshPhysicalMaterial({
          color: 0x1f6e4f,
          emissive: 0x0c2b21,
          emissiveIntensity: 0.4,
          metalness: 0.1,
          roughness: 0.1,
          transmission: 0.7,
          thickness: 1.2,
          clearcoat: 1,
          clearcoatRoughness: 0.15,
        }),
      );
      gem.scale.setScalar(0.001);
      rig.add(gem);

      function makeGlowTexture() {
        const s = 256;
        const cv = document.createElement("canvas");
        cv.width = cv.height = s;
        const ctx = cv.getContext("2d")!;
        const g = ctx.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
        g.addColorStop(0, "rgba(90,220,170,0.85)");
        g.addColorStop(0.4, "rgba(47,156,112,0.35)");
        g.addColorStop(1, "rgba(47,156,112,0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, s, s);
        return new THREE.CanvasTexture(cv);
      }
      const glow = new THREE.Sprite(
        new THREE.SpriteMaterial({ map: makeGlowTexture(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }),
      );
      glow.scale.setScalar(0.001);
      rig.add(glow);

      function makeDustTexture() {
        const s = 64;
        const cv = document.createElement("canvas");
        cv.width = cv.height = s;
        const ctx = cv.getContext("2d")!;
        const g = ctx.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
        g.addColorStop(0, "rgba(255,244,220,0.9)");
        g.addColorStop(1, "rgba(255,244,220,0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, s, s);
        return new THREE.CanvasTexture(cv);
      }
      const DUST_COUNT = 46;
      const dustGeo = new THREE.BufferGeometry();
      const dustPositions = new Float32Array(DUST_COUNT * 3);
      const dustSpeeds: number[] = [];
      for (let di = 0; di < DUST_COUNT; di++) {
        dustPositions[di * 3] = (Math.random() - 0.5) * 10;
        dustPositions[di * 3 + 1] = (Math.random() - 0.5) * 8;
        dustPositions[di * 3 + 2] = (Math.random() - 0.5) * 8;
        dustSpeeds.push(0.0015 + Math.random() * 0.0025);
      }
      dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPositions, 3));
      const dust = new THREE.Points(
        dustGeo,
        new THREE.PointsMaterial({
          size: 0.06,
          map: makeDustTexture(),
          transparent: true,
          opacity: 0.32,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
          sizeAttenuation: true,
        }),
      );
      rig.add(dust);

      const ringDefs = [
        { r: 1.9, tube: 0.03, color: 0xc9a463, tilt: 0.5 },
        { r: 2.5, tube: 0.026, color: 0x9aa0a6, tilt: -0.28 },
        { r: 3.15, tube: 0.03, color: 0xc9a463, tilt: 0.14 },
      ];
      const rings = ringDefs.map((def, i) => {
        const mesh = new THREE.Mesh(
          new THREE.TorusGeometry(def.r, def.tube, 16, 100),
          new THREE.MeshStandardMaterial({ color: def.color, metalness: 1, roughness: 0.3 }),
        );
        mesh.rotation.x = Math.PI / 2 + def.tilt;
        mesh.rotation.y = i * 0.6;
        mesh.scale.setScalar(0.001);
        rig.add(mesh);
        return mesh;
      });

      function makeCoinFaceTexture(symbolRotation: number) {
        const size = 512, cx = size / 2, cy = size / 2, R = size / 2 - 4;
        const cv = document.createElement("canvas");
        cv.width = cv.height = size;
        const ctx = cv.getContext("2d")!;

        const base = ctx.createRadialGradient(cx - 70, cy - 70, 20, cx, cy, R);
        base.addColorStop(0, "#ecd9ac");
        base.addColorStop(0.38, "#c9a463");
        base.addColorStop(0.72, "#8a6d3b");
        base.addColorStop(1, "#4f3c20");
        ctx.fillStyle = base;
        ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();

        ctx.save();
        ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.clip();
        for (let a = 0; a < 360; a += 1.1) {
          const rad = (a * Math.PI) / 180;
          ctx.strokeStyle = `rgba(255,255,255,${0.03 + Math.random() * 0.05})`;
          ctx.lineWidth = 0.6;
          ctx.beginPath();
          ctx.moveTo(cx + Math.cos(rad) * R * 0.18, cy + Math.sin(rad) * R * 0.18);
          ctx.lineTo(cx + Math.cos(rad) * R, cy + Math.sin(rad) * R);
          ctx.stroke();
        }
        ctx.restore();

        ctx.strokeStyle = "rgba(30,22,10,0.4)";
        ctx.lineWidth = 9;
        ctx.beginPath(); ctx.arc(cx, cy, R - 7, 0, Math.PI * 2); ctx.stroke();
        ctx.strokeStyle = "rgba(255,240,210,0.55)";
        ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.arc(cx, cy, R - 15, 0, Math.PI * 2); ctx.stroke();
        ctx.strokeStyle = "rgba(60,180,130,0.5)";
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(cx, cy, R * 0.6, 0, Math.PI * 2); ctx.stroke();

        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(symbolRotation || 0);
        ctx.font = `700 ${Math.floor(R * 0.92)}px Georgia, 'Times New Roman', serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "rgba(35,25,10,0.55)";
        ctx.fillText("₿", 5, 7);
        ctx.fillStyle = "#f6ecd0";
        ctx.fillText("₿", 0, 0);
        ctx.restore();

        const vg = ctx.createRadialGradient(cx, cy, R * 0.55, cx, cy, R);
        vg.addColorStop(0, "rgba(0,0,0,0)");
        vg.addColorStop(1, "rgba(0,0,0,0.4)");
        ctx.fillStyle = vg;
        ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();

        const tex = new THREE.CanvasTexture(cv);
        tex.anisotropy = 4;
        return tex;
      }

      function makeCoinEdgeTexture() {
        const w = 256, h = 32;
        const cv = document.createElement("canvas");
        cv.width = w; cv.height = h;
        const ctx = cv.getContext("2d")!;
        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, "#f0e2ba");
        grad.addColorStop(0.5, "#a9873f");
        grad.addColorStop(1, "#4f3c20");
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = "rgba(0,0,0,0.45)";
        ctx.lineWidth = 1;
        for (let x = 0; x < w; x += 3) {
          ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
        }
        const tex = new THREE.CanvasTexture(cv);
        tex.wrapS = THREE.RepeatWrapping;
        tex.repeat.x = 10;
        return tex;
      }

      const edgeMaterial = new THREE.MeshStandardMaterial({ map: makeCoinEdgeTexture(), metalness: 0.9, roughness: 0.4 });
      const coinGeo = new THREE.CylinderGeometry(1, 1, 0.22, 64);

      const COIN_COUNT = 6;
      const coins: THREE.Mesh[] = [];
      for (let ci = 0; ci < COIN_COUNT; ci++) {
        const faceTex = makeCoinFaceTexture((ci % 3) * 0.35 - 0.35);
        const faceMat = new THREE.MeshStandardMaterial({ map: faceTex, metalness: 0.82, roughness: 0.3 });
        const coin = new THREE.Mesh(coinGeo, [edgeMaterial, faceMat, faceMat]);
        coin.scale.setScalar(0.001);
        coin.castShadow = true;
        coin.receiveShadow = true;
        rig.add(coin);
        coins.push(coin);
      }

      const stackY = -((COIN_COUNT - 1) * 0.24) / 2;
      const stacked = coins.map((_coin, i) => ({
        pos: new THREE.Vector3(0, stackY + i * 0.24, 0),
        rotY: (i * 7 - 10) * (Math.PI / 180),
        rotXZ: 0,
        scale: 1,
      }));

      const opened = [
        { pos: new THREE.Vector3(-1.9, -0.5, 2.6), rotY: -0.35, rotXZ: 0.12, scale: 1.3 },
        { pos: new THREE.Vector3(0.3, 1.9, 1.7), rotY: 0.5, rotXZ: -0.08, scale: 1.15 },
        { pos: new THREE.Vector3(2.2, 0.9, 0.2), rotY: -0.2, rotXZ: 0.18, scale: 1.0 },
        { pos: new THREE.Vector3(-2.6, 1.5, -1.3), rotY: 0.65, rotXZ: -0.15, scale: 0.78 },
        { pos: new THREE.Vector3(2.4, -1.4, -1.6), rotY: -0.55, rotXZ: 0.1, scale: 0.74 },
        { pos: new THREE.Vector3(-0.4, -2.0, -2.4), rotY: 0.3, rotXZ: -0.2, scale: 0.66 },
      ];

      resize = () => {
        const w = canvas.clientWidth, h = canvas.clientHeight;
        renderer!.setSize(w, h, false);
        camera!.aspect = w / (h || 1);
        camera!.updateProjectionMatrix();
      };
      window.addEventListener("resize", resize);
      cleanups.push(() => window.removeEventListener("resize", resize!));
      resize();

      let spin = 0;
      const onVisibility = () => {
        running = !document.hidden;
        if (running && sceneReady) rafId = requestAnimationFrame(tick!);
      };
      document.addEventListener("visibilitychange", onVisibility);
      cleanups.push(() => document.removeEventListener("visibilitychange", onVisibility));

      applyProgress = (p: number) => {
        const openT = easeInOutCubic(Math.min(p / 0.85, 1));

        gem.scale.setScalar(lerp(0.001, 1.05, openT));
        glow.scale.setScalar(lerp(0.001, 2.6, openT));

        rings.forEach((mesh, i) => {
          mesh.scale.setScalar(lerp(0.001, 1.3 + i * 0.08, openT));
          mesh.position.z = lerp(0, (i - 1) * 1.4, openT);
        });

        coins.forEach((coin, i) => {
          const from = stacked[i], to = opened[i];
          coin.position.lerpVectors(from.pos, to.pos, openT);
          coin.rotation.y = lerp(from.rotY, to.rotY, openT);
          coin.rotation.x = lerp(from.rotXZ, to.rotXZ, openT) * 0.6;
          coin.rotation.z = lerp(from.rotXZ, to.rotXZ, openT) * 0.4;
          coin.scale.setScalar(lerp(from.scale, to.scale, openT));
        });

        camera!.position.z = lerp(9.6, 8, openT);
        camera!.position.x = Math.sin(p * Math.PI) * 0.7;
        camera!.lookAt(0, 0, 0);
      };

      tick = () => {
        if (!running || disposed) return;
        spin += 0.0016;
        rings.forEach((mesh, i) => {
          mesh.rotation.z += 0.0014 * (i % 2 === 0 ? 1 : -1);
        });
        gem.rotation.y = spin * 1.3;
        gem.rotation.x = Math.sin(spin * 0.7) * 0.12;
        (glow.material as THREE.SpriteMaterial).opacity = 0.85 + Math.sin(spin * 2.2) * 0.1;
        camera!.position.y = Math.sin(spin * 0.6) * 0.08;

        const dustPos = dust.geometry.attributes.position.array as Float32Array;
        for (let k = 0; k < DUST_COUNT; k++) {
          dustPos[k * 3 + 1] += dustSpeeds[k];
          if (dustPos[k * 3 + 1] > 4.2) dustPos[k * 3 + 1] = -4.2;
        }
        dust.geometry.attributes.position.needsUpdate = true;

        renderer!.render(scene!, camera!);
        rafId = requestAnimationFrame(tick!);
      };

      applyProgress(0);
      renderer.render(scene, camera);
      sceneReady = true;

      cleanups.push(() => {
        renderer!.dispose();
        scene!.traverse((obj) => {
          if (obj instanceof THREE.Mesh) {
            obj.geometry.dispose();
            const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
            mats.forEach((m) => m.dispose());
          }
        });
      });
    } catch (sceneError) {
      sceneReady = false;
      console.warn("Landing hero scene failed to initialize, using fallback visual:", sceneError);
    }

    if (reduce) {
      if (sceneReady) {
        applyProgress!(0.7);
        renderer!.render(scene!, camera!);
      }
      statement.style.opacity = "1";
      eyebrow.style.opacity = "0";
      nav.classList.add("is-visible");
      nav.style.opacity = "1";
      return () => cleanups.forEach((fn) => fn());
    }

    gsap.registerPlugin(ScrollTrigger);
    const lenis = new Lenis({ smoothWheel: true, duration: 1.1 });
    const lenisRaf = (time: number) => { lenis.raf(time); requestAnimationFrame(lenisRaf); };
    const lenisRafId = requestAnimationFrame(lenisRaf);
    lenis.on("scroll", ScrollTrigger.update);
    const tickerFn = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tickerFn);
    gsap.ticker.lagSmoothing(0);
    cleanups.push(() => {
      cancelAnimationFrame(lenisRafId);
      gsap.ticker.remove(tickerFn);
      lenis.destroy();
    });

    if (sceneReady) rafId = requestAnimationFrame(tick!);

    const heroTrigger = ScrollTrigger.create({
      trigger: heroRef.current!,
      start: "top top",
      end: "bottom bottom",
      scrub: true,
      onUpdate: (self) => {
        const p = self.progress;
        if (sceneReady) applyProgress!(p);
        eyebrow.style.opacity = String(Math.max(0, 1 - p / 0.22));
        const textP = Math.max(0, Math.min((p - 0.62) / 0.3, 1));
        statement.style.opacity = String(textP);
        progressFill.style.width = `${(p * 100).toFixed(1)}%`;
      },
    });

    const navTrigger = ScrollTrigger.create({
      trigger: heroRef.current!,
      start: "bottom 85%",
      end: "bottom 45%",
      scrub: true,
      onUpdate: (self) => {
        nav.style.opacity = String(self.progress);
        if (self.progress > 0.02) nav.classList.add("is-visible");
        else nav.classList.remove("is-visible");
      },
    });

    ScrollTrigger.refresh();

    return () => {
      disposed = true;
      running = false;
      cancelAnimationFrame(rafId);
      heroTrigger.kill();
      navTrigger.kill();
      cleanups.forEach((fn) => fn());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------------- premium polish layer ----------------
  useEffect(() => {
    const root = rootRef.current;
    const heroStage = heroStageRef.current;
    if (!root) return;

    const cleanups: Array<() => void> = [];

    try {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
      gsap.registerPlugin(ScrollTrigger);

      // ---- page load sequence ----
      const loader = loaderRef.current;
      if (loader) {
        if (reduce) {
          loader.style.display = "none";
        } else {
          const loaderFill = loaderFillRef.current;
          const loaderMark = loaderMarkRef.current;
          if (loaderFill && loaderMark) {
            const tl = gsap.timeline();
            tl.to(loaderMark, { opacity: 1, duration: 0.3, ease: "power1.out" })
              .to(loaderFill, { width: "100%", duration: 0.7, ease: "power2.inOut" }, 0.1)
              .add(() => {
                loader.classList.add("is-done");
                setTimeout(() => { loader.style.display = "none"; }, 550);
              }, 0.85);
            cleanups.push(() => tl.kill());
          }
        }
      }

      // ---- global scroll progress ----
      const scrollProgress = scrollProgressRef.current;
      const bodyTrigger = scrollProgress
        ? ScrollTrigger.create({
            trigger: root,
            start: "top top",
            end: "bottom bottom",
            scrub: true,
            onUpdate: (self) => {
              scrollProgress.style.width = `${(self.progress * 100).toFixed(1)}%`;
            },
          })
        : undefined;
      if (bodyTrigger) cleanups.push(() => bodyTrigger.kill());

      // ---- custom cursor ----
      if (fine && !reduce) {
        root.classList.add("has-cursor");
        const dot = cursorDotRef.current;
        const ring = cursorRingRef.current;
        if (dot && ring) {
          let mx = window.innerWidth / 2, my = window.innerHeight / 2;
          let rx = mx, ry = my;
          const onMove = (e: MouseEvent) => {
            mx = e.clientX; my = e.clientY;
            dot.style.transform = `translate(${mx}px,${my}px) translate(-50%,-50%)`;
          };
          window.addEventListener("mousemove", onMove);
          cleanups.push(() => window.removeEventListener("mousemove", onMove));

          let cursorRaf = 0;
          const cursorTick = () => {
            rx += (mx - rx) * 0.16;
            ry += (my - ry) * 0.16;
            ring.style.transform = `translate(${rx}px,${ry}px) translate(-50%,-50%)`;
            cursorRaf = requestAnimationFrame(cursorTick);
          };
          cursorRaf = requestAnimationFrame(cursorTick);
          cleanups.push(() => cancelAnimationFrame(cursorRaf));

          const hoverables = root.querySelectorAll("button, a, [data-tilt]");
          const onEnter = () => ring.classList.add("is-active");
          const onLeave = () => ring.classList.remove("is-active");
          hoverables.forEach((el) => {
            el.addEventListener("mouseenter", onEnter);
            el.addEventListener("mouseleave", onLeave);
          });
          cleanups.push(() => {
            hoverables.forEach((el) => {
              el.removeEventListener("mouseenter", onEnter);
              el.removeEventListener("mouseleave", onLeave);
            });
          });
        }
      }

      // ---- magnetic buttons ----
      if (fine && !reduce) {
        const magnets = root.querySelectorAll<HTMLElement>("[data-magnetic]");
        const onMove = function (this: HTMLElement, e: Event) {
          const me = e as MouseEvent;
          const r = this.getBoundingClientRect();
          const relX = me.clientX - (r.left + r.width / 2);
          const relY = me.clientY - (r.top + r.height / 2);
          this.style.transform = `translate(${(relX * 0.28).toFixed(1)}px,${(relY * 0.35).toFixed(1)}px)`;
        };
        const onLeave = function (this: HTMLElement) { this.style.transform = ""; };
        magnets.forEach((btn) => {
          btn.addEventListener("mousemove", onMove);
          btn.addEventListener("mouseleave", onLeave);
        });
        cleanups.push(() => {
          magnets.forEach((btn) => {
            btn.removeEventListener("mousemove", onMove);
            btn.removeEventListener("mouseleave", onLeave);
          });
        });
      }

      // ---- card tilt + cursor-tracked spotlight ----
      if (fine && !reduce) {
        const cards = root.querySelectorAll<HTMLElement>("[data-tilt]");
        const onMove = function (this: HTMLElement, e: Event) {
          const me = e as MouseEvent;
          const r = this.getBoundingClientRect();
          const px = (me.clientX - r.left) / r.width;
          const py = (me.clientY - r.top) / r.height;
          const rotY = (px - 0.5) * 8;
          const rotX = (0.5 - py) * 8;
          this.style.transform = `perspective(900px) rotateX(${rotX.toFixed(2)}deg) rotateY(${rotY.toFixed(2)}deg) translateZ(4px)`;
          this.style.setProperty("--mx", `${(px * 100).toFixed(1)}%`);
          this.style.setProperty("--my", `${(py * 100).toFixed(1)}%`);
        };
        const onLeave = function (this: HTMLElement) { this.style.transform = ""; };
        cards.forEach((card) => {
          card.addEventListener("mousemove", onMove);
          card.addEventListener("mouseleave", onLeave);
        });
        cleanups.push(() => {
          cards.forEach((card) => {
            card.removeEventListener("mousemove", onMove);
            card.removeEventListener("mouseleave", onLeave);
          });
        });
      }

      // ---- word-split reveal for the manifesto lede ----
      const lede = manifestoLedeRef.current;
      if (lede) {
        const wordEls = lede.querySelectorAll(".reveal-word");
        if (!reduce) {
          const tween = gsap.to(wordEls, {
            opacity: 1,
            filter: "blur(0px)",
            y: 0,
            duration: 0.6,
            ease: "power2.out",
            stagger: 0.018,
            scrollTrigger: { trigger: lede, start: "top 85%" },
          });
          cleanups.push(() => tween.scrollTrigger?.kill());
        }
      }

      // ---- section reveal choreography ----
      const triggers: ScrollTrigger[] = [];
      if (!reduce) {
        root.querySelectorAll(".reveal-fade").forEach((el) => {
          const tw = gsap.to(el, { opacity: 1, y: 0, duration: 0.8, ease: "power3.out", scrollTrigger: { trigger: el, start: "top 88%" } });
          if (tw.scrollTrigger) triggers.push(tw.scrollTrigger);
        });
        root.querySelectorAll(".reveal-blur").forEach((el) => {
          const tw = gsap.to(el, { opacity: 1, filter: "blur(0px)", duration: 0.9, ease: "power2.out", scrollTrigger: { trigger: el, start: "top 88%" } });
          if (tw.scrollTrigger) triggers.push(tw.scrollTrigger);
        });
        root.querySelectorAll(".reveal-scale").forEach((el) => {
          const tw = gsap.to(el, { opacity: 1, scale: 1, duration: 0.7, ease: "back.out(1.4)", scrollTrigger: { trigger: el, start: "top 85%" } });
          if (tw.scrollTrigger) triggers.push(tw.scrollTrigger);
        });
        root.querySelectorAll(".reveal-clip").forEach((el) => {
          const tw = gsap.to(el, { clipPath: "inset(0 0 0% 0)", duration: 0.9, ease: "power4.inOut", scrollTrigger: { trigger: el, start: "top 88%" } });
          if (tw.scrollTrigger) triggers.push(tw.scrollTrigger);
        });
        root.querySelectorAll("[data-stagger]").forEach((group) => {
          const tw = gsap.to(group.children, {
            opacity: 1, y: 0, duration: 0.6, ease: "power2.out", stagger: 0.09,
            scrollTrigger: { trigger: group, start: "top 88%" },
          });
          if (tw.scrollTrigger) triggers.push(tw.scrollTrigger);
        });
      }
      cleanups.push(() => triggers.forEach((t) => t.kill()));

      // ---- financial health: bars fill and the score counts up, once ----
      const health = healthRef.current;
      const dialNum = dialNumRef.current;
      const dialArc = dialArcRef.current;
      if (health && dialNum && dialArc) {
        const healthTrigger = ScrollTrigger.create({
          trigger: health,
          start: "top 75%",
          once: true,
          onEnter: () => {
            const bars = health.querySelectorAll<HTMLElement>("[data-bar]");
            if (reduce) {
              bars.forEach((b) => { b.style.width = b.getAttribute("data-target") ?? "0%"; });
              dialNum.textContent = HEALTH_SCORE.toFixed(1);
              dialArc.style.strokeDashoffset = String(DIAL_CIRCUMFERENCE * (1 - HEALTH_SCORE / 100));
              return;
            }
            bars.forEach((b, i) => {
              gsap.to(b, { width: b.getAttribute("data-target") ?? "0%", duration: 1, delay: i * 0.08, ease: "power2.out" });
            });
            const counter = { v: 0 };
            gsap.to(counter, {
              v: HEALTH_SCORE,
              duration: 1.3,
              ease: "power2.out",
              onUpdate: () => {
                dialNum.textContent = counter.v.toFixed(1);
                dialArc.style.strokeDashoffset = String(DIAL_CIRCUMFERENCE * (1 - counter.v / 100));
              },
            });
          },
        });
        cleanups.push(() => healthTrigger.kill());
      }

      // ---- mouse-following ambient light in the hero ----
      if (fine && !reduce && heroStage) {
        const heroGlow = document.createElement("div");
        heroGlow.style.cssText =
          "position:absolute;inset:0;z-index:1;pointer-events:none;opacity:0;transition:opacity 0.4s ease;" +
          "background:radial-gradient(circle 320px at var(--gx,50%) var(--gy,50%), rgba(201,164,99,0.09), transparent 70%);";
        heroStage.appendChild(heroGlow);
        const onMove = (e: MouseEvent) => {
          const r = heroStage.getBoundingClientRect();
          heroGlow.style.setProperty("--gx", `${(((e.clientX - r.left) / r.width) * 100).toFixed(1)}%`);
          heroGlow.style.setProperty("--gy", `${(((e.clientY - r.top) / r.height) * 100).toFixed(1)}%`);
          heroGlow.style.opacity = "1";
        };
        const onLeave = () => { heroGlow.style.opacity = "0"; };
        heroStage.addEventListener("mousemove", onMove);
        heroStage.addEventListener("mouseleave", onLeave);
        cleanups.push(() => {
          heroStage.removeEventListener("mousemove", onMove);
          heroStage.removeEventListener("mouseleave", onLeave);
          heroGlow.remove();
        });
      }
    } catch (polishError) {
      console.warn("Landing polish layer failed to initialize:", polishError);
    }

    return () => cleanups.forEach((fn) => fn());
  }, []);

  return (
    <div className="landing" ref={rootRef}>
      <div className="loader" ref={loaderRef}>
        <span className="loader-mark" ref={loaderMarkRef}>FINMENTOR</span>
        <div className="loader-bar"><div className="loader-bar-fill" ref={loaderFillRef} /></div>
      </div>

      <div className="page-grain" />
      <div className="scroll-progress" ref={scrollProgressRef} />
      <div className="cursor-ring" ref={cursorRingRef} />
      <div className="cursor-dot" ref={cursorDotRef} />

      <nav className="nav" ref={navRef}>
        <span className="nav-mark">FINMENTOR</span>
        <Link to="/signup" className="nav-cta" data-magnetic>Sign up</Link>
      </nav>

      <section className="hero" ref={heroRef}>
        <div className="hero-stage" ref={heroStageRef}>
          <div className="hero-eyebrow" ref={eyebrowRef}><span className="mono">FINANCIAL STRUCTURE</span></div>
          <div className="hero-fallback" />
          <canvas className="hero-canvas" ref={canvasRef} />
          <div className="hero-vignette" />
          <div className="hero-grain" />
          <div className="hero-statement" ref={statementRef}>
            <h1>Understand the <em>structure</em> behind your financial life.</h1>
          </div>
          <div className="hero-progress"><div className="hero-progress-fill" ref={progressFillRef} /></div>
        </div>
      </section>

      <section className="manifesto" style={{ position: "relative", overflow: "hidden" }}>
        <div className="ambient-blob a" style={{ width: 420, height: 420, left: -120, top: -60, background: "radial-gradient(circle, rgba(47,156,112,0.28), transparent 70%)" }} />
        <div className="ambient-blob b" style={{ width: 340, height: 340, right: -100, bottom: -80, background: "radial-gradient(circle, rgba(201,164,99,0.16), transparent 70%)" }} />
        <div className="wrap">
          <p className="lede" ref={manifestoLedeRef}>
            <SplitWords text="FinMentor is not a dashboard of numbers." />{" "}
            <span className="dim"><SplitWords text="It is a deterministic model of where you actually stand, built from your own data, explained in plain language, one decision at a time." /></span>
          </p>
          <p className="sub reveal-fade">No projections dressed up as facts. No manufactured urgency. Every figure on this page after the fold comes from your account, or it is marked as an example.</p>
        </div>
      </section>

      <section className="block" id="health" ref={healthRef}>
        <div className="wrap">
          <span className="kicker">Financial health</span>
          <h2 className="reveal-blur">One score, five honest components.</h2>
          <p className="intro reveal-fade">Savings rate, emergency fund, debt load, budget stability, and goal progress, each scored out of twenty. Higher is always better, and every point traces back to a real transaction.</p>
          <div className="health-layout">
            <div className="health-dial reveal-scale">
              <svg viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="52" fill="none" stroke="#171a15" strokeWidth={8} />
                <circle
                  ref={dialArcRef}
                  cx="60" cy="60" r="52" fill="none" stroke="#2f9c70" strokeWidth={8}
                  strokeLinecap="round"
                  strokeDasharray={DIAL_CIRCUMFERENCE}
                  strokeDashoffset={DIAL_CIRCUMFERENCE}
                  transform="rotate(-90 60 60)"
                />
              </svg>
              <div className="center-num">
                <span className="n mono" ref={dialNumRef}>0</span>
                <span className="label">out of 100</span>
              </div>
            </div>
            <div className="health-components" data-stagger>
              {HEALTH_COMPONENTS.map((c) => (
                <div className="health-row" key={c.name}>
                  <span className="name">{c.name}</span>
                  <div className="bar-track"><div className="bar-fill" data-bar style={{ width: "0%" }} data-target={`${c.target}%`} /></div>
                  <span className="val mono">{c.points}</span>
                </div>
              ))}
            </div>
          </div>
          <span className="sample-tag">Example data, not yours until you sign up</span>
        </div>
      </section>

      <section className="block" id="twin-dna" style={{ position: "relative", overflow: "hidden" }}>
        <div className="ambient-blob a" style={{ width: 380, height: 380, right: -140, top: "10%", background: "radial-gradient(circle, rgba(201,164,99,0.14), transparent 70%)" }} />
        <div className="wrap">
          <span className="kicker">Twin &amp; DNA</span>
          <h2 className="reveal-clip">A model of you, and the pattern behind it.</h2>
          <p className="intro reveal-fade">The Financial Twin mirrors your accounts, income and obligations as one live structure. Financial DNA is the recurring pattern underneath it, the habits that quietly compound.</p>
          <div className="duo">
            <div className="duo-card reveal-fade" data-tilt>
              <h3>Financial Twin</h3>
              <p>Twelve buckets: income, fixed costs, variable spend, debt, savings, and more, sized to what is actually in your accounts.</p>
              <div className="twin-viz">
                {Array.from({ length: 12 }, (_, i) => (
                  <div className={`cell${i % 3 === 0 ? " on" : ""}`} key={i} />
                ))}
              </div>
            </div>
            <div className="duo-card reveal-fade" data-tilt>
              <h3>Financial DNA</h3>
              <p>The traits your history reveals: how consistently you save, how you react to a shortfall, how goals get funded.</p>
              <div className="dna-strand">
                {["CONSISTENT SAVER", "DEBT-AVERSE", "GOAL-DRIVEN", "VARIABLE INCOME"].map((tag) => (
                  <div className="dna-row" key={tag}>
                    <span className="dot" /><span className="line" /><span className="tag mono">{tag}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <span className="sample-tag">Example data, not yours until you sign up</span>
        </div>
      </section>

      <section className="block" id="capabilities">
        <div className="wrap">
          <span className="kicker">The rest of the system</span>
          <h2 className="reveal-blur">Everything below the score.</h2>
          <div className="capabilities-grid" data-stagger>
            {CAPABILITIES.map((c) => (
              <div className="cap-cell" data-tilt key={c.n}>
                <span className="n mono">{c.n}</span>
                <h4>{c.title}</h4>
                <p>{c.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="cta-block" style={{ position: "relative", overflow: "hidden" }}>
        <div className="ambient-blob a" style={{ width: 500, height: 500, left: "50%", top: -160, transform: "translateX(-50%)", background: "radial-gradient(circle, rgba(47,156,112,0.3), transparent 70%)" }} />
        <div className="wrap">
          <h2 className="reveal-scale">Your financial structure, understood.</h2>
          <div className="cta-actions reveal-fade">
            <Link to="/signup" className="btn-primary" data-magnetic>Sign up</Link>
            <a href="#health" className="btn-ghost" data-magnetic>See how it works</a>
          </div>
        </div>
      </section>

      <footer className="wrap">
        <span>FinMentor</span>
        <Link to="/login" className="link-underline">Already have an account? Sign in</Link>
      </footer>
    </div>
  );
}
