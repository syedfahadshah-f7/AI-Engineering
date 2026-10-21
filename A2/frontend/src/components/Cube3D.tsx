import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Sticker } from "../api";

// Western colour scheme: white top, green front.
export const FACE_COLOURS: Record<string, string> = {
  U: "#f4f4f2",
  R: "#d62828",
  F: "#1fa149",
  D: "#ffd60a",
  L: "#ff7b1c",
  B: "#1d5fd6",
};

const NORMALS: Record<string, [number, number, number]> = {
  U: [0, 1, 0],
  R: [1, 0, 0],
  F: [0, 0, 1],
  D: [0, -1, 0],
  L: [-1, 0, 0],
  B: [0, 0, -1],
};

export interface CubeStep {
  move: string;
  state: string; // authoritative state after the move (from the server engine)
}

interface Props {
  stickers: Sticker[];
  initialState: string; // changes => reset (new puzzle)
  steps: CubeStep[]; // appended as the model plays
}

function roundedSquare(size: number, r: number) {
  const s = size / 2;
  const shape = new THREE.Shape();
  shape.moveTo(-s + r, -s);
  shape.lineTo(s - r, -s);
  shape.quadraticCurveTo(s, -s, s, -s + r);
  shape.lineTo(s, s - r);
  shape.quadraticCurveTo(s, s, s - r, s);
  shape.lineTo(-s + r, s);
  shape.quadraticCurveTo(-s, s, -s, s - r);
  shape.lineTo(-s, -s + r);
  shape.quadraticCurveTo(-s, -s, -s + r, -s);
  return new THREE.ShapeGeometry(shape);
}

interface Piece {
  obj: THREE.Object3D;
  cubie: THREE.Vector3; // home cubie position (layer membership)
  home: THREE.Matrix4;
}

export default function Cube3D({ stickers, initialState, steps }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const api = useRef<{
    setState: (s: string) => void;
    animate: (move: string, ms: number) => Promise<void>;
  } | null>(null);
  const applied = useRef(0);
  const generation = useRef(0); // bumps on every new puzzle to abort stale animations
  const queue = useRef<Promise<void>>(Promise.resolve());
  const stepsRef = useRef(steps);
  stepsRef.current = steps;

  // Build the scene once per mount.
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || stickers.length !== 54) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
    camera.position.set(5.2, 4.4, 6.4);
    camera.lookAt(0, 0, 0);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 1.6));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(4, 8, 6);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.6);
    fill.position.set(-6, -2, -4);
    scene.add(fill);

    const root = new THREE.Group();
    scene.add(root);
    const pieces: Piece[] = [];

    const bodyGeo = new THREE.BoxGeometry(0.97, 0.97, 0.97);
    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x141414, roughness: 0.6 });
    for (let x = -1; x <= 1; x++)
      for (let y = -1; y <= 1; y++)
        for (let z = -1; z <= 1; z++) {
          const m = new THREE.Mesh(bodyGeo, bodyMat);
          m.position.set(x, y, z);
          m.updateMatrix();
          root.add(m);
          pieces.push({ obj: m, cubie: new THREE.Vector3(x, y, z), home: m.matrix.clone() });
        }

    const stickerGeo = roundedSquare(0.84, 0.12);
    const stickerMats: THREE.MeshStandardMaterial[] = [];
    for (const s of stickers) {
      const mat = new THREE.MeshStandardMaterial({ color: FACE_COLOURS[s.face], roughness: 0.35 });
      stickerMats[s.index] = mat;
      const mesh = new THREE.Mesh(stickerGeo, mat);
      const n = new THREE.Vector3(...s.normal);
      const p = new THREE.Vector3(...s.position);
      mesh.position.copy(p.clone().add(n.clone().multiplyScalar(0.492)));
      mesh.lookAt(mesh.position.clone().add(n));
      mesh.updateMatrix();
      root.add(mesh);
      pieces.push({ obj: mesh, cubie: p, home: mesh.matrix.clone() });
    }

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableZoom = false;
    controls.enablePan = false;
    controls.rotateSpeed = 0.7;

    const resize = () => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(mount);
    resize();

    let raf = 0;
    const loop = () => {
      controls.update();
      renderer.render(scene, camera);
      raf = requestAnimationFrame(loop);
    };
    loop();

    const resetTransforms = () => {
      for (const p of pieces) {
        if (p.obj.parent !== root) root.add(p.obj);
        p.obj.matrix.copy(p.home);
        p.obj.matrix.decompose(p.obj.position, p.obj.quaternion, p.obj.scale);
      }
    };

    api.current = {
      setState: (state: string) => {
        resetTransforms();
        for (let i = 0; i < 54; i++) stickerMats[i].color.set(FACE_COLOURS[state[i]] ?? "#888");
      },
      animate: (move: string, ms: number) =>
        new Promise<void>((resolve) => {
          const face = move[0];
          const axis = new THREE.Vector3(...NORMALS[face]);
          const turns = move.endsWith("2") ? 2 : move.endsWith("'") ? -1 : 1;
          const target = -turns * (Math.PI / 2); // clockwise seen from the face
          const pivot = new THREE.Group();
          root.add(pivot);
          for (const p of pieces) if (Math.round(p.cubie.dot(axis)) === 1) pivot.attach(p.obj);
          const start = performance.now();
          const step = (now: number) => {
            const k = Math.min(1, (now - start) / ms);
            const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
            pivot.setRotationFromAxisAngle(axis, target * e);
            if (k < 1) requestAnimationFrame(step);
            else {
              root.remove(pivot);
              resolve();
            }
          };
          requestAnimationFrame(step);
        }),
    };

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      bodyGeo.dispose();
      stickerGeo.dispose();
      stickerMats.forEach((m) => m.dispose());
      mount.removeChild(renderer.domElement);
      api.current = null;
    };
  }, [stickers]);

  // New puzzle: show its start state immediately.
  useEffect(() => {
    applied.current = 0;
    generation.current += 1;
    queue.current = Promise.resolve();
    api.current?.setState(initialState);
  }, [initialState, stickers]);

  // Animate any moves not yet shown, one after another. If the model is
  // faster than the animation, shorten the turns so the cube keeps up.
  useEffect(() => {
    const pending = steps.length - applied.current;
    if (pending <= 0) return;
    const startIdx = applied.current;
    applied.current = steps.length;
    const gen = generation.current;
    queue.current = queue.current.then(async () => {
      for (let i = startIdx; i < stepsRef.current.length && i < startIdx + pending; i++) {
        const cube = api.current;
        if (!cube || gen !== generation.current) return;
        const backlog = stepsRef.current.length - i;
        const ms = backlog > 3 ? 90 : backlog > 1 ? 160 : 260;
        await cube.animate(stepsRef.current[i].move, ms);
        if (gen !== generation.current) return;
        cube.setState(stepsRef.current[i].state);
      }
    });
  }, [steps, initialState]);

  return <div className="cube3d" ref={mountRef} />;
}
