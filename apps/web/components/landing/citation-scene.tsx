'use client'

/**
 * The hero: one contract page, in 3D, being cited.
 *
 * Not a backdrop. This is the product's mechanic performed on a real clause —
 * a highlighter runs across the sentence, and the extracted value appears
 * beside it, which is exactly what a cell in the grid is. The three targets
 * are the same three questions the grid below the fold asks.
 *
 * The page is a canvas texture laid out here, so the highlight rectangles are
 * measured from the same text run that drew it: the mark cannot drift off the
 * sentence. three is imported inside the effect, the way the PDF viewer
 * imports pdf.js, so it stays out of the server render and the first chunk.
 */

import { useEffect, useRef, useState } from 'react'

const TEX_W = 1000
const TEX_H = 1414
const MARGIN = 96
const LEADING = 34

const PAPER = '#ffffff'
const INK = '#1a1917'
const FAINT = '#6b6862'

type Block = { text: string; kind: 'title' | 'party' | 'heading' | 'body'; target?: number }

const BLOCKS: Block[] = [
  { kind: 'title', text: 'MASTER SERVICES AGREEMENT' },
  { kind: 'party', text: 'Northwind Systems Limited  ·  Halcyon Software Limited' },
  { kind: 'heading', text: '8.  LIMITATION OF LIABILITY' },
  {
    kind: 'body',
    target: 0,
    text: '8.1  Subject to clause 8.3, the aggregate liability of the Supplier under this Agreement shall not exceed 125% of the Fees paid or payable in the twelve (12) months preceding the event giving rise to the claim.',
  },
  {
    kind: 'body',
    text: '8.2  Nothing in this Agreement operates to exclude or limit liability for death or personal injury caused by negligence, or for fraud or fraudulent misrepresentation.',
  },
  { kind: 'heading', text: '9.  TERM AND RENEWAL' },
  {
    kind: 'body',
    target: 1,
    text: '9.1  This Agreement continues for an Initial Term of twenty-four (24) months and renews automatically for successive periods of twelve (12) months unless either party gives not less than ninety (90) days written notice.',
  },
  { kind: 'heading', text: '12.  GOVERNING LAW' },
  {
    kind: 'body',
    target: 2,
    text: '12.1  This Agreement and any dispute arising out of or in connection with it are governed by the laws of England and Wales.',
  },
]

const TARGETS = [
  { question: 'Liability cap', answer: '125% of the Fees' },
  { question: 'Auto-renewal', answer: 'Yes, 12 months' },
  { question: 'Governing law', answer: 'England and Wales' },
]

type Rect = { x: number; y: number; w: number; h: number }

/** Draws the page and returns the rectangle each target sentence occupies. */
function drawPage(ctx: CanvasRenderingContext2D): Rect[] {
  ctx.fillStyle = PAPER
  ctx.fillRect(0, 0, TEX_W, TEX_H)

  const width = TEX_W - MARGIN * 2
  const rects: Rect[] = []
  let y = MARGIN + 40

  const wrap = (text: string): string[] => {
    const words = text.split(' ')
    const lines: string[] = []
    let line = ''
    for (const word of words) {
      const candidate = line ? `${line} ${word}` : word
      if (ctx.measureText(candidate).width > width && line) {
        lines.push(line)
        line = word
      } else {
        line = candidate
      }
    }
    if (line) lines.push(line)
    return lines
  }

  for (const block of BLOCKS) {
    if (block.kind === 'title') {
      ctx.font = '600 30px Georgia, "Times New Roman", serif'
      ctx.fillStyle = INK
      ctx.textAlign = 'center'
      ctx.fillText(block.text, TEX_W / 2, y)
      ctx.textAlign = 'left'
      y += 44
      continue
    }
    if (block.kind === 'party') {
      ctx.font = '400 19px Georgia, "Times New Roman", serif'
      ctx.fillStyle = FAINT
      ctx.textAlign = 'center'
      ctx.fillText(block.text, TEX_W / 2, y)
      ctx.textAlign = 'left'
      y += 34
      ctx.strokeStyle = '#e0ddd6'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(MARGIN, y)
      ctx.lineTo(TEX_W - MARGIN, y)
      ctx.stroke()
      y += 52
      continue
    }
    if (block.kind === 'heading') {
      ctx.font = '600 21px Georgia, "Times New Roman", serif'
      ctx.fillStyle = INK
      ctx.fillText(block.text, MARGIN, y)
      y += 42
      continue
    }

    ctx.font = '400 21px Georgia, "Times New Roman", serif'
    ctx.fillStyle = INK
    const lines = wrap(block.text)
    const top = y - 22
    for (const line of lines) {
      ctx.fillText(line, MARGIN, y)
      y += LEADING
    }
    if (block.target !== undefined) {
      rects[block.target] = {
        x: MARGIN - 6,
        y: top,
        w: width + 12,
        h: lines.length * LEADING - 4,
      }
    }
    y += 26
  }

  return rects
}

const HOLD = 3.1 // seconds a citation stays up
const GROW = 0.55 // seconds the highlighter takes to cross the sentence
const CYCLE = HOLD + GROW

export function CitationScene() {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const chipRef = useRef<HTMLDivElement | null>(null)
  const [active, setActive] = useState(0)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const host = hostRef.current
    const chip = chipRef.current
    if (!host || !chip) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let disposed = false
    let cleanup: (() => void) | undefined

    void (async () => {
      let THREE: typeof import('three')
      try {
        THREE = await import('three')
      } catch {
        return
      }
      if (disposed) return

      let renderer: import('three').WebGLRenderer
      try {
        renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
      } catch {
        return // No WebGL. The section keeps its space and stays empty.
      }

      const canvas = document.createElement('canvas')
      canvas.width = TEX_W
      canvas.height = TEX_H
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const rects = drawPage(ctx)

      const texture = new THREE.CanvasTexture(canvas)
      texture.colorSpace = THREE.SRGBColorSpace
      texture.anisotropy = renderer.capabilities.getMaxAnisotropy()

      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      renderer.setSize(host.clientWidth, host.clientHeight, false)
      renderer.domElement.style.width = '100%'
      renderer.domElement.style.height = '100%'
      renderer.domElement.style.display = 'block'
      host.appendChild(renderer.domElement)

      const scene = new THREE.Scene()
      const camera = new THREE.PerspectiveCamera(30, host.clientWidth / host.clientHeight, 0.1, 50)
      camera.position.set(0, 0, 5.4)

      const PAGE_W = 2.4
      const PAGE_H = (PAGE_W * TEX_H) / TEX_W

      // A blurred quad behind the sheet. Cheaper and steadier than a light and
      // a shadow map, and all this needs is to lift the page off the paper.
      const shadowCanvas = document.createElement('canvas')
      shadowCanvas.width = 256
      shadowCanvas.height = 362
      const shadowCtx = shadowCanvas.getContext('2d')
      if (shadowCtx) {
        shadowCtx.filter = 'blur(18px)'
        shadowCtx.fillStyle = '#3a352c'
        shadowCtx.fillRect(34, 34, shadowCanvas.width - 68, shadowCanvas.height - 68)
      }
      const shadow = new THREE.Mesh(
        new THREE.PlaneGeometry(PAGE_W * 1.3, PAGE_H * 1.22),
        new THREE.MeshBasicMaterial({
          map: new THREE.CanvasTexture(shadowCanvas),
          transparent: true,
          opacity: 0.4,
          depthWrite: false,
        }),
      )
      shadow.position.set(0.03, -0.05, -0.01)

      const page = new THREE.Mesh(
        new THREE.PlaneGeometry(PAGE_W, PAGE_H),
        new THREE.MeshBasicMaterial({ map: texture, transparent: false }),
      )
      const group = new THREE.Group()
      group.add(shadow)
      group.add(page)
      group.rotation.set(0.05, -0.16, 0.012)
      // Nudged left so the chip has room beside the sentence it points at.
      group.position.x = -0.22
      scene.add(group)

      // Highlighter. Anchored left so growing it reads as a pen stroke.
      const markGeometry = new THREE.PlaneGeometry(1, 1)
      const markMaterial = new THREE.MeshBasicMaterial({
        color: new THREE.Color('#e9aa2f'),
        transparent: true,
        opacity: 0,
        depthWrite: false,
      })
      const mark = new THREE.Mesh(markGeometry, markMaterial)
      mark.position.z = 0.002
      group.add(mark)

      const toLocal = (rect: Rect) => ({
        w: (rect.w / TEX_W) * PAGE_W,
        h: (rect.h / TEX_H) * PAGE_H,
        cx: ((rect.x + rect.w / 2) / TEX_W - 0.5) * PAGE_W,
        cy: (0.5 - (rect.y + rect.h / 2) / TEX_H) * PAGE_H,
      })

      const projected = new THREE.Vector3()
      const pointer = { x: 0, y: 0 }
      const eased = { x: 0, y: 0 }
      let current = -1

      const placeChip = (rect: Rect, progress: number) => {
        const local = toLocal(rect)
        projected.set(local.cx + local.w / 2, local.cy, 0.02)
        group.localToWorld(projected)
        projected.project(camera)
        const x = (projected.x * 0.5 + 0.5) * host.clientWidth
        const y = (-projected.y * 0.5 + 0.5) * host.clientHeight
        // Keep it inside the stage; on a narrow column the sentence ends close
        // to the edge and an unclamped chip hangs off the page.
        const maxX = Math.max(0, host.clientWidth - chip.offsetWidth)
        const maxY = Math.max(0, host.clientHeight - chip.offsetHeight)
        chip.style.transform =
          `translate(${Math.min(Math.max(x - 18, 0), maxX)}px, ` +
          `${Math.min(Math.max(y - 20, 0), maxY)}px)`
        chip.style.opacity = String(progress)
      }

      const applyFrame = (time: number) => {
        const index = Math.floor(time / CYCLE) % TARGETS.length
        const local = time % CYCLE
        const rect = rects[index]
        if (!rect) return

        if (index !== current) {
          current = index
          setActive(index)
        }

        const grow = Math.min(local / GROW, 1)
        // easeOutCubic: the pen decelerates at the end of the sentence.
        const eased01 = 1 - Math.pow(1 - grow, 3)
        const fade = local > CYCLE - 0.45 ? Math.max(0, (CYCLE - local) / 0.45) : 1

        const l = toLocal(rect)
        mark.scale.set(Math.max(l.w * eased01, 0.0001), l.h, 1)
        mark.position.x = l.cx - l.w / 2 + (l.w * eased01) / 2
        mark.position.y = l.cy
        markMaterial.opacity = 0.32 * fade

        placeChip(rect, eased01 * fade)

        eased.x += (pointer.x - eased.x) * 0.05
        eased.y += (pointer.y - eased.y) * 0.05
        group.rotation.y = -0.16 + eased.x * 0.08
        group.rotation.x = 0.05 + eased.y * 0.05

        renderer.render(scene, camera)
      }

      const resize = () => {
        const { clientWidth: w, clientHeight: h } = host
        if (w === 0 || h === 0) return
        renderer.setSize(w, h, false)
        camera.aspect = w / h
        camera.updateProjectionMatrix()
      }
      const observer = new ResizeObserver(resize)
      observer.observe(host)

      const onPointerMove = (event: PointerEvent) => {
        const box = host.getBoundingClientRect()
        pointer.x = ((event.clientX - box.left) / box.width) * 2 - 1
        pointer.y = ((event.clientY - box.top) / box.height) * 2 - 1
      }

      let visible = true
      const intersection = new IntersectionObserver(
        (entries) => {
          const entry = entries[0]
          if (entry) visible = entry.isIntersecting
        },
        { threshold: 0 },
      )
      intersection.observe(host)

      setReady(true)
      let frame = 0
      const start = performance.now()

      if (reduced) {
        applyFrame(GROW + 0.6) // first citation, already drawn
      } else {
        window.addEventListener('pointermove', onPointerMove, { passive: true })
        const loop = (now: number) => {
          frame = requestAnimationFrame(loop)
          if (!visible || document.hidden) return
          applyFrame((now - start) / 1000)
        }
        frame = requestAnimationFrame(loop)
      }

      cleanup = () => {
        cancelAnimationFrame(frame)
        window.removeEventListener('pointermove', onPointerMove)
        observer.disconnect()
        intersection.disconnect()
        texture.dispose()
        page.geometry.dispose()
        ;(page.material as import('three').Material).dispose()
        shadow.geometry.dispose()
        ;(shadow.material as import('three').MeshBasicMaterial).map?.dispose()
        ;(shadow.material as import('three').Material).dispose()
        markGeometry.dispose()
        markMaterial.dispose()
        renderer.dispose()
        renderer.domElement.remove()
      }
    })()

    return () => {
      disposed = true
      cleanup?.()
    }
  }, [])

  const target = TARGETS[active]

  return (
    <div className="landing-stage">
      <div ref={hostRef} className="absolute inset-0" aria-hidden />
      <div
        ref={chipRef}
        aria-hidden
        className="landing-chip"
        style={{ opacity: 0, visibility: ready ? 'visible' : 'hidden' }}
      >
        <span className="landing-chip-q">{target?.question}</span>
        <span className="landing-chip-a">{target?.answer}</span>
      </div>
      <p className="sr-only">
        A page of a master services agreement. Each highlighted sentence is the source of one answer
        in the review grid below.
      </p>
    </div>
  )
}
