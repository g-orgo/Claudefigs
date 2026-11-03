import { expect, test } from 'claude-code/testing'

// Draws the detail view through the engine, seeding the atoms a poll would have written.

const child = { id: 'abcd1234', sessionId: 'abcd1234-0000', name: 'split-x', label: 'Acompanhamento', title: 'Acompanhamento', prompt_head: 'p', cwd: '/w', index: 1, total: 1, group: 'g1', parent: 'parent-1', isRunning: true, isWaiting: false, after: [], startedMs: 0 }
const group = { group: 'g1', parent: 'parent-1', parentCwd: '/w', parentTitle: 'Pai', startedMs: 0, children: [child] }

for (const surface of ['terminal', 'desktop'] as const) {
  test(`the detail view draws its header and transcript on ${surface}`, async ($, on) => {
    on('session.start', (_, e) => ({ cwd: e.cwd }))
    on('command.register', () => ({ value: { command: 'x' } }))
    on('ui.open', () => ({ value: { isPlaced: true } }))
    const seed: Record<string, unknown> = {
      groups: { shape: 'groups-1', value: [group] },
      view: { shape: 'view-2', value: { mode: 'detail', kind: 'child', id: 'abcd1234', group: 'g1' } },
      transcript: { shape: 'transcript-3', value: { id: 'abcd1234', available: true, subagents: 0, lines: [{ role: 'voce', text: 'oi' }, { role: 'claude', text: 'ola' }] } },
    }
    on('state.get', (_: any, e: any) => ({ value: { value: seed[e.key], version: seed[e.key] ? 1 : 0 } }))
    on('session.id' as any, () => ({ value: 'me-0000' }))
    on('clock.now' as any, () => ({ value: 1000 }))
    on('session.cwd' as any, () => ({ value: '/w' }))
    const ui = await $.ui.mount({ plugin: 'prompt-splitter', component: 'Pane', requestId: 'split-sessions', surface,
      props: { title: 'Splits', isFocused: false, bodyColumns: 40, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} } } as any)
    expect((await ui.find({ type: 'Text', text: /Acompanhamento/ }))?.text).toBe('Acompanhamento')
    expect((await ui.find({ type: 'Text', text: /ola/ }))?.text).toBe('ola')
    await ui.unmount()
  })
}
