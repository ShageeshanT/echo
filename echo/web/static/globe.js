/* Three.js dot-globe — port of the Python DotGlobe.
 *
 *   - 7000 points on a Fibonacci sphere lattice
 *   - Continuous Y-axis rotation (slight wobble on X)
 *   - RMS-reactive: deformation factor + color brightness scale with audio
 *   - Sleep mode: 0.15x brightness, slow breathing
 */

import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";

const NUM_DOTS = 7000;

export class DotGlobe {
    constructor(container) {
        this.container = container;
        this.rms = 0;
        this.brightness = 0.15;          // sleep starts dim
        this.targetBrightness = 0.15;
        this.tick = 0;

        // ── scene ──
        this.scene = new THREE.Scene();

        // ── camera ──
        const w = container.clientWidth, h = container.clientHeight;
        this.camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);
        this.camera.position.z = 4;

        // ── renderer ──
        this.renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.setSize(w, h);
        this.renderer.setClearColor(0x000000, 0);  // transparent
        container.appendChild(this.renderer.domElement);

        // ── geometry: spherical Fibonacci lattice (matches Python code) ──
        const positions = new Float32Array(NUM_DOTS * 3);
        const phis = new Float32Array(NUM_DOTS);
        for (let i = 0; i < NUM_DOTS; i++) {
            const phi = Math.acos(1.0 - 2.0 * (i + 0.5) / NUM_DOTS);
            const theta = Math.PI * (1 + Math.sqrt(5)) * i;
            positions[i*3+0] = Math.sin(phi) * Math.cos(theta);
            positions[i*3+1] = Math.sin(phi) * Math.sin(theta);
            positions[i*3+2] = Math.cos(phi);
            phis[i] = phi;
        }
        this.basePositions = positions.slice();

        const geom = new THREE.BufferGeometry();
        geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        this.geom = geom;

        // ── shader-like material: PointsMaterial with vertex colors so we
        //    can set per-point color/brightness based on z-depth ──
        const colors = new Float32Array(NUM_DOTS * 3);
        for (let i = 0; i < NUM_DOTS; i++) {
            colors[i*3+0] = 0.82;
            colors[i*3+1] = 0.91;
            colors[i*3+2] = 1.00;
        }
        geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));
        this.colors = colors;

        const mat = new THREE.PointsMaterial({
            size: 0.018,
            vertexColors: true,
            transparent: true,
            opacity: 0.95,
            sizeAttenuation: true,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
        });
        this.points = new THREE.Points(geom, mat);
        this.scene.add(this.points);

        // ── ambient glow (faint sphere behind the dots) ──
        const glowGeom = new THREE.SphereGeometry(0.95, 32, 32);
        const glowMat = new THREE.MeshBasicMaterial({
            color: 0x2a1548, transparent: true, opacity: 0.06,
        });
        this.glow = new THREE.Mesh(glowGeom, glowMat);
        this.scene.add(this.glow);

        // ── handle resize ──
        this._onResize = this._onResize.bind(this);
        window.addEventListener("resize", this._onResize);

        // ── animation loop ──
        this._loop = this._loop.bind(this);
        this._loop();
    }

    setRms(v)              { this.rms = v; }
    setBrightnessTarget(b) { this.targetBrightness = b; }
    setSleeping(sleeping)  { this.targetBrightness = sleeping ? 0.15 : 1.0; }

    _onResize() {
        const w = this.container.clientWidth, h = this.container.clientHeight;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    }

    _loop() {
        this.tick++;
        const t = this.tick / 60;

        // Smooth brightness toward target
        this.brightness += (this.targetBrightness - this.brightness) * 0.04;

        // Rotation — slow Y, gentle wobble on X
        this.points.rotation.y = t * 0.35 + this.rms * t * 0.2;
        this.points.rotation.x = 0.35 + Math.sin(t * 0.15) * 0.15;
        this.points.rotation.z = Math.sin(t * 0.1) * 0.08;

        // RMS-reactive scale (modest — keep the sphere shape recognizable)
        const scale = 1 + this.rms * 0.18;
        this.points.scale.setScalar(scale);

        // Per-vertex deformation: pulse out slightly with RMS, bias by z so
        // the front face puffs more visibly on speech.
        const pos = this.geom.attributes.position.array;
        const base = this.basePositions;
        const deform = 1 + this.rms * 0.12;
        for (let i = 0; i < NUM_DOTS; i++) {
            const ix = i*3;
            pos[ix+0] = base[ix+0] * deform;
            pos[ix+1] = base[ix+1] * deform;
            pos[ix+2] = base[ix+2] * deform;
        }
        this.geom.attributes.position.needsUpdate = true;

        // Color: brightness scaled by `this.brightness`, plus z-front bonus
        // is implicit because Three.js Points already does perspective size
        // attenuation. We just modulate overall brightness here.
        // (Doing per-frame color mutation is too slow at 7k dots — instead
        //  we adjust material opacity, which is essentially the same look.)
        this.points.material.opacity = 0.25 + 0.7 * this.brightness;
        this.glow.material.opacity = 0.04 + 0.06 * this.brightness;

        this.renderer.render(this.scene, this.camera);
        requestAnimationFrame(this._loop);
    }
}
