import { expect, test } from 'claude-code/testing'

const BAND = { plugin: 'bom-senso-band', surface: 'terminal', component: 'AbovePrompt' } as const

// Stands for what the poller stored: the pending example and the last tick.
const seed = (on: any, pending: unknown, now: number) =>
  on('state.get', (_: unknown, e: { key: string }) => ({
    value: { value: e.key === 'pending' ? pending : now, version: 0 },
  }))

test('a pending example shows its countdown and can be declined', async ($, on) => {
  const runs: string[][] = []
  on('process.run', (_, e) => {
    runs.push([...e.argv])

    return { value: { exitCode: 0, stdout: 'Recusado: abc\n', stderr: '' } }
  })
  seed(on, { id: 'abc', rule: 'Regra de teste', deadline: 20_000 }, 5_000)

  const ui = await $.ui.mount({ ...BAND, props: { hasSurvey: false } })
  expect(await ui.find({ type: 'Text', text: /aceito em 15s/ })).toBeDefined()
  await ui.press({ key: 'decline' })
  expect(runs.some(argv => argv.includes('decline'))).toBe(true)
  await ui.unmount()
})

test('an expired example shows nothing', async ($, on) => {
  seed(on, { id: 'abc', rule: 'r', deadline: 1_000 }, 5_000)

  const ui = await $.ui.mount({ ...BAND, props: { hasSurvey: false } })
  expect(await ui.find({ type: 'Button' })).toBeUndefined()
  await ui.unmount()
})
