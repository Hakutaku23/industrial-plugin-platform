import { spawnSync } from 'node:child_process'
import { existsSync, readdirSync, rmSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(scriptDir, '..')
const frontendDir = join(repoRoot, 'frontend')
const frontendSrcDir = join(frontendDir, 'src')
const cleanOnly = process.argv.includes('--clean-only')

if (!cleanOnly) {
  runBuild()
}

const removed = cleanGeneratedSourceFiles(frontendSrcDir)
if (removed.length > 0) {
  console.log(`Cleaned ${removed.length} generated frontend source file(s):`)
  for (const file of removed) {
    console.log(`- ${file}`)
  }
} else {
  console.log('No generated frontend source files needed cleanup.')
}

function runBuild() {
  const result = spawnSync('npm', ['--prefix', 'frontend', 'run', 'build:raw'], {
    cwd: repoRoot,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  })
  if (result.error) {
    throw result.error
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}

function cleanGeneratedSourceFiles(rootDir) {
  const removed = []
  for (const file of walkFiles(rootDir)) {
    const candidate = cleanupCandidate(file)
    if (!candidate) continue
    rmSync(file, { force: true })
    removed.push(relativeToRepo(file))
  }
  return removed.sort()
}

function cleanupCandidate(file) {
  if (file.endsWith('.vue.js')) {
    return existsSync(file.slice(0, -3))
  }
  if (file.endsWith('.vue.js.map')) {
    return existsSync(file.slice(0, -7))
  }
  if (file.endsWith('.js')) {
    return existsSync(`${file.slice(0, -3)}.ts`)
  }
  if (file.endsWith('.js.map')) {
    return existsSync(`${file.slice(0, -7)}.ts`)
  }
  return false
}

function* walkFiles(rootDir) {
  if (!existsSync(rootDir)) return
  for (const entry of readdirSync(rootDir)) {
    const path = join(rootDir, entry)
    const stats = statSync(path)
    if (stats.isDirectory()) {
      yield* walkFiles(path)
    } else if (stats.isFile()) {
      yield path
    }
  }
}

function relativeToRepo(file) {
  return file.slice(repoRoot.length + 1).replaceAll('\\', '/')
}
