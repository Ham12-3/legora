'use client'

/**
 * The hero background: a drifting archive of contract pages, drawn as one
 * instanced draw call.
 *
 * three is loaded lazily inside the effect so it never reaches the server
 * render and never lands in the initial route chunk — the same reason the PDF
 * viewer imports pdf.js the way it does.
 *
 * The page body contributes no light (additive blending on a near-black
 * ground), so what you see is the text itself: ruled lines whose lengths come
 * from a per-instance seed, a citation bar on roughly one page in four, and a
 * slow horizontal sweep standing in for review passing through the corpus.
 */

import { useEffect, useRef } from 'react'

const PAGE_COUNT = 58
const A4 = 1.414

const VERTEX = /* glsl */ `
  attribute float aSeed;
  varying vec2 vUv;
  varying float vSeed;
  varying float vWorldY;
  varying float vViewDepth;

  void main() {
    vUv = uv;
    vSeed = aSeed;
    vec4 world = modelMatrix * instanceMatrix * vec4(position, 1.0);
    vWorldY = world.y;
    vec4 viewPosition = viewMatrix * world;
    vViewDepth = -viewPosition.z;
    gl_Position = projectionMatrix * viewPosition;
  }
`

const FRAGMENT = /* glsl */ `
  precision highp float;

  uniform float uSweepY;
  uniform vec3 uInk;
  uniform vec3 uAmber;
  uniform float uOpacity;

  varying vec2 vUv;
  varying float vSeed;
  varying float vWorldY;
  varying float vViewDepth;

  const float ROWS = 24.0;

  float hash(float n) {
    return fract(sin(n * 127.1) * 43758.5453123);
  }

  void main() {
    // --- ruled text -------------------------------------------------------
    float row = floor(vUv.y * ROWS);
    float rowFrac = fract(vUv.y * ROWS);
    // Lines sit in the upper part of each row band; the gap below is leading.
    float band = smoothstep(0.30, 0.36, rowFrac) * (1.0 - smoothstep(0.60, 0.66, rowFrac));

    float margin = 0.12;
    // Ragged right edge: every line stops somewhere different.
    float lineEnd = 1.0 - margin - 0.34 * hash(vSeed + row * 7.3);
    // A blank row here and there reads as a paragraph break.
    float present = step(0.16, hash(vSeed * 2.7 + row));
    float ink = band * present
      * step(margin, vUv.x)
      * (1.0 - smoothstep(lineEnd - 0.012, lineEnd, vUv.x));

    vec3 color = uInk * ink;

    // --- the citation -----------------------------------------------------
    // Some pages carry a quoted span: one row, amber, brighter than the text
    // around it, with a soft halo so it reads as a highlight and not a typo.
    float cited = step(0.74, hash(vSeed + 11.0));
    float citedRow = floor(hash(vSeed * 5.1) * (ROWS - 6.0)) + 3.0;
    float onCitedRow = 1.0 - step(0.5, abs(row - citedRow));
    float highlight = cited * onCitedRow * band * present * step(margin, vUv.x)
      * (1.0 - smoothstep(lineEnd - 0.012, lineEnd, vUv.x));
    float halo = cited * exp(-pow((vUv.y * ROWS - citedRow - 0.48) * 1.9, 2.0)) * 0.16;
    color = mix(color, uAmber * 1.35, highlight);
    color += uAmber * halo;

    // --- page edge --------------------------------------------------------
    float edge = (1.0 - smoothstep(0.0, 0.012, vUv.x)) + smoothstep(0.988, 1.0, vUv.x)
      + (1.0 - smoothstep(0.0, 0.009, vUv.y)) + smoothstep(0.991, 1.0, vUv.y);
    color += uInk * 0.30 * clamp(edge, 0.0, 1.0);

    // --- review sweep -----------------------------------------------------
    float d = vWorldY - uSweepY;
    color += uInk * 0.55 * exp(-d * d * 1.4) * max(ink, clamp(edge, 0.0, 1.0) * 0.5);

    // --- depth ------------------------------------------------------------
    float fog = exp(-max(vViewDepth - 6.0, 0.0) * 0.055);
    float alpha = clamp(max(max(ink, highlight), clamp(edge, 0.0, 1.0) * 0.5) + halo, 0.0, 1.0);

    gl_FragColor = vec4(color, alpha * fog * uOpacity);
    if (gl_FragColor.a < 0.002) discard;
  }
`

export function DocumentField() {
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let disposed = false
    let cleanup: (() => void) | undefined

    void (async () => {
      let THREE: typeof import('three')
      try {
        THREE = await import('three')
      } catch {
        return // No WebGL bundle, no hero. The CSS ground stands on its own.
      }
      if (disposed) return

      let renderer: import('three').WebGLRenderer
      try {
        renderer = new THREE.WebGLRenderer({
          alpha: true,
          antialias: true,
          powerPreference: 'high-performance',
        })
      } catch {
        return // WebGL unavailable or blocked.
      }

      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      renderer.setSize(host.clientWidth, host.clientHeight, false)
      renderer.domElement.style.width = '100%'
      renderer.domElement.style.height = '100%'
      renderer.domElement.style.display = 'block'
      host.appendChild(renderer.domElement)

      const scene = new THREE.Scene()
      const camera = new THREE.PerspectiveCamera(42, host.clientWidth / host.clientHeight, 0.1, 120)
      camera.position.set(0, 0, 11)

      const group = new THREE.Group()
      scene.add(group)

      const geometry = new THREE.PlaneGeometry(1, A4)
      const seeds = new Float32Array(PAGE_COUNT)
      for (let i = 0; i < PAGE_COUNT; i += 1) seeds[i] = Math.random() * 100
      geometry.setAttribute('aSeed', new THREE.InstancedBufferAttribute(seeds, 1))

      // Held directly rather than reached through material.uniforms, which is
      // an index signature and therefore optional at every lookup.
      const uSweepY = { value: 0 }
      const uOpacity = { value: 0 }

      const material = new THREE.ShaderMaterial({
        vertexShader: VERTEX,
        fragmentShader: FRAGMENT,
        uniforms: {
          uSweepY,
          uOpacity,
          uInk: { value: new THREE.Color('#63788f') },
          uAmber: { value: new THREE.Color('#e0a33c') },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      })

      const mesh = new THREE.InstancedMesh(geometry, material, PAGE_COUNT)
      mesh.frustumCulled = false
      group.add(mesh)

      type Page = {
        base: import('three').Vector3
        scale: number
        tiltY: number
        tiltZ: number
        phase: number
        speed: number
      }

      const pages: Page[] = []
      for (let i = 0; i < PAGE_COUNT; i += 1) {
        pages.push({
          // Biased right: the copy sits on the left and the field is
          // atmosphere behind it, not wallpaper under it.
          base: new THREE.Vector3(
            5 + (Math.random() - 0.5) * 30,
            (Math.random() - 0.5) * 20,
            -26 + Math.random() * 28,
          ),
          scale: 1.7 + Math.random() * 1.5,
          tiltY: (Math.random() - 0.5) * 0.7,
          tiltZ: (Math.random() - 0.5) * 0.12,
          phase: Math.random() * Math.PI * 2,
          speed: 0.12 + Math.random() * 0.22,
        })
      }

      const dummy = new THREE.Object3D()
      const pointer = { x: 0, y: 0 }
      const eased = { x: 0, y: 0 }

      const writeMatrices = (time: number) => {
        pages.forEach((page, i) => {
          const bob = Math.sin(time * page.speed + page.phase)
          dummy.position.set(
            page.base.x + bob * 0.22,
            page.base.y + Math.cos(time * page.speed * 0.8 + page.phase) * 0.3,
            page.base.z,
          )
          dummy.rotation.set(0, page.tiltY + bob * 0.05, page.tiltZ)
          dummy.scale.setScalar(page.scale)
          dummy.updateMatrix()
          mesh.setMatrixAt(i, dummy.matrix)
        })
        mesh.instanceMatrix.needsUpdate = true
      }

      const resize = () => {
        const { clientWidth: w, clientHeight: h } = host
        if (w === 0 || h === 0) return
        renderer.setSize(w, h, false)
        camera.aspect = w / h
        camera.updateProjectionMatrix()
      }

      const onPointerMove = (event: PointerEvent) => {
        pointer.x = (event.clientX / window.innerWidth) * 2 - 1
        pointer.y = (event.clientY / window.innerHeight) * 2 - 1
      }

      const observer = new ResizeObserver(resize)
      observer.observe(host)

      let visible = true
      const intersection = new IntersectionObserver(
        (entries) => {
          const entry = entries[0]
          if (entry) visible = entry.isIntersecting
        },
        { threshold: 0 },
      )
      intersection.observe(host)

      let frame = 0
      const start = performance.now()

      const renderFrame = (now: number) => {
        const time = (now - start) / 1000
        // Fade in rather than popping once the shader compiles.
        uOpacity.value = Math.min(time / 2.2, 1) * 0.8
        uSweepY.value = ((time * 1.1) % 30) - 15

        eased.x += (pointer.x - eased.x) * 0.04
        eased.y += (pointer.y - eased.y) * 0.04
        group.rotation.y = Math.sin(time * 0.045) * 0.06 + eased.x * 0.1
        group.rotation.x = eased.y * 0.05
        camera.position.x = eased.x * 0.9
        camera.position.y = -eased.y * 0.6
        camera.lookAt(0, 0, -6)

        writeMatrices(time)
        renderer.render(scene, camera)
      }

      const loop = (now: number) => {
        frame = requestAnimationFrame(loop)
        if (!visible || document.hidden) return
        renderFrame(now)
      }

      if (reduced) {
        // One composed frame, no animation loop.
        uOpacity.value = 0.8
        uSweepY.value = 40
        writeMatrices(0)
        renderer.render(scene, camera)
      } else {
        window.addEventListener('pointermove', onPointerMove, { passive: true })
        frame = requestAnimationFrame(loop)
      }

      cleanup = () => {
        cancelAnimationFrame(frame)
        window.removeEventListener('pointermove', onPointerMove)
        observer.disconnect()
        intersection.disconnect()
        geometry.dispose()
        material.dispose()
        renderer.dispose()
        renderer.domElement.remove()
      }
    })()

    return () => {
      disposed = true
      cleanup?.()
    }
  }, [])

  return <div ref={hostRef} aria-hidden className="absolute inset-0" />
}
