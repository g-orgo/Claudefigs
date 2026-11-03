import { expect, mock, test } from 'claude-code/testing'

import { VIEWER_COMMANDS, VIEWER_DROP, VIEWER_ROWS, viewerDrop } from './register'

// The read-only, full-screen viewer that `claude split` opens (CLAUDE_SPLIT_VIEWER=1).

test('viewerDrop refuses plain prompts and commands outside the allow list', () => {
  expect(viewerDrop({})).toBe(VIEWER_DROP)
  expect(viewerDrop({ command: { name: 'compact' } })).toBe(VIEWER_DROP)
  expect(viewerDrop({ command: { name: 'prompt-splitter:split' } })).toBe(VIEWER_DROP)
})

test('viewerDrop lets the pane commands and exit run', () => {
  for (const name of VIEWER_COMMANDS) expect(viewerDrop({ command: { name } })).toBeUndefined()
})

// Answers the engine calls a viewer session makes, recording each pane open; returns the mocked clock.
function viewerEngine(on: any, env: string | undefined, opens: any[]) {
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('command.register', () => ({ value: { command: 'x' } }))
  on('ui.open', (_: any, e: any) => {
    opens.push(e)
    return { value: { isPlaced: true } }
  })
  on('ui.status' as any, () => ({ value: undefined }))
  on('env.get' as any, (_: any, e: any) => ({ value: e.name === 'CLAUDE_SPLIT_VIEWER' ? env : undefined }))
  on('session.id' as any, () => ({ value: 'me-0000' }))
  on('session.cwd' as any, () => ({ value: '/w' }))
  on('fs.read' as any, () => ({ value: '' }))
  on('process.run' as any, () => ({ value: { exitCode: 0, stdout: '[]', stderr: '' } }))
  return mock.clock(on, { now: 1000 })
}

const SPLITS = { command: 'splits', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false } }
const fullHeight = (o: any) => o.id === 'split-sessions' && o.rows === VIEWER_ROWS && o.focus === true

test('in viewer mode the pane opens by itself, focused and full height', async ($, on) => {
  const opens: any[] = []
  const clock = viewerEngine(on, '1', opens)
  await ($ as any).session.start({ cwd: '/w', source: 'startup' })
  await clock.advance(1)
  expect(opens.some(fullHeight)).toBe(true)
})

test('in viewer mode /splits opens the full height pane and typed prompts are dropped', async ($, on) => {
  const opens: any[] = []
  viewerEngine(on, '1', opens)
  let reached = false
  on('prompt.submit', (_: any, e: any) => {
    reached = true
    return { text: e.text }
  })
  await ($ as any).session.start({ cwd: '/w', source: 'startup' })
  opens.length = 0
  expect((await ($ as any).command.run(SPLITS)).text).toBe('Painel Splits aberto.')
  expect(opens.every(fullHeight) && opens.length > 0).toBe(true)
  const result = await $.prompt.submit({ text: 'apague tudo' })
  expect(result.drop).toBe(VIEWER_DROP)
  expect(reached).toBe(false)
})

test('outside viewer mode prompts pass, nothing opens at start and /splits keeps the default size', async ($, on) => {
  const opens: any[] = []
  const clock = viewerEngine(on, undefined, opens)
  on('prompt.submit', (_: any, e: any) => ({ text: e.text }))
  await ($ as any).session.start({ cwd: '/w', source: 'startup' })
  await clock.advance(1)
  expect(opens.length).toBe(0)
  expect((await $.prompt.submit({ text: 'oi' })).drop).toBeUndefined()
  await ($ as any).command.run(SPLITS)
  expect(opens.length > 0 && opens.every(o => o.rows === undefined)).toBe(true)
})
