// Copy pdf.js (main module + worker) into public/ so the viewer loads them as
// plain static files with a native `import()`. pdf.js's build is itself a
// webpack bundle and breaks when re-bundled by Next in dev mode
// ("Object.defineProperty called on non-object"). A CDN would work but would
// make the viewer depend on a third party, even though no document data is
// ever sent to it.
import { copyFileSync, mkdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const here = dirname(fileURLToPath(import.meta.url))
const build = join(dirname(require.resolve('pdfjs-dist/package.json')), 'build')
const publicDir = join(here, '..', 'public')

mkdirSync(publicDir, { recursive: true })
for (const name of ['pdf.min.mjs', 'pdf.worker.min.mjs']) {
  copyFileSync(join(build, name), join(publicDir, name))
  console.log(`pdf.js: ${name} -> public/`)
}
