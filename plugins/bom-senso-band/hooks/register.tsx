import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Pending } from '../types'

const pending = atom({ plugin: 'bom-senso-band', key: 'pending' } as const, null)
const now = atom({ plugin: 'bom-senso-band', key: 'now' } as const, 0)

const RULE_LIMIT = 90

export const register: Register = on => {
  let home = ''
  let session = ''

  const statePath = () => `${home}/.claude/state/bom-senso/pending.json`
  const storePath = () => `${home}/.claude/local-plugins/plugins/bom-senso/scripts/store.py`

  on('session.start', async ($, e, next) => {
    const env = await $.process.hookEnv()
    session = env.CLAUDE_CODE_SESSION_ID ?? ''
    home = (await $.process.run(['printenv', 'HOME'])).stdout.trim()

    $.clock.every(1000, async () => {
      if (!home || !session) return
      const t = await $.clock.now()
      let item: Pending | null = null
      try {
        if (await $.fs.exists(statePath())) {
          const rows = JSON.parse(await $.fs.read(statePath())) as Record<string, Pending>
          const row = rows[session]
          item = row && row.deadline > t ? row : null
        }
      } catch {
        item = null
      }
      const current = await read($, pending)
      if (item === null && current === null) return
      await update($, pending, () => item)
      await update($, now, () => t)
    })

    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const item = await read($, pending)
    const t = await read($, now)
    if (e.props.hasSurvey || item === null || item.deadline <= t) {
      return next(e)
    }

    const { Box, Button, Text } = $.ui.resolve(e)
    const seconds = Math.max(1, Math.ceil((item.deadline - t) / 1000))
    const rule = item.rule.length > RULE_LIMIT ? `${item.rule.slice(0, RULE_LIMIT - 3)}...` : item.rule

    const decline = async (alsoMute: boolean) => {
      await update($, pending, () => null)
      const argv = ['python3', storePath(), 'decline', session, ...(alsoMute ? ['--mute'] : [])]
      const { exitCode, stdout } = await $.process.run(argv)
      $.ui.toast(exitCode === 0 ? `Bom senso: ${stdout.trim()}` : 'Bom senso: falha ao recusar o exemplo')
    }

    return (
      <Box>
        <Text color="yellow">Bom senso: novo exemplo </Text>
        <Text dimColor>"{rule}" (aceito em {seconds}s) </Text>
        <Button key="decline" label="Nao registrar" onPress={() => decline(false)} />
        <Button key="mute" label="Nao perguntar mais" onPress={() => decline(true)} />
      </Box>
    )
  })
}
