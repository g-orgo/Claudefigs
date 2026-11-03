// Shared shapes of the split pane of the prompt-splitter plugin. Engine types come from 'claude-code'.

export type SplitRecord = {
  id: string
  name: string
  cwd: string
  prompt_head?: string
  started: string | number
  parent: string
  group: string
  // Written by dispatch.py from now on; older records lack them.
  index?: number
  total?: number
  parent_transcript?: string
  parent_cwd?: string
  // Descriptive pt-BR title written by dispatch.py from now on.
  title?: string
  // Execution order of the item and the indices it waits on; 'waiting' marks a not yet launched item.
  state?: string
  after?: number[]
  // Chain position: the chain number, the step inside it, its length and the display label ("K" or "K.S").
  chain?: number
  step?: number
  chain_len?: number
  label?: string
  mode?: 'sync' | 'async'
}

export type ChildRow = {
  id: string
  sessionId: string
  name: string
  label: string
  group: string
  cwd: string
  startedMs: number
  isRunning: boolean
  index: number
  total: number
  parent: string
  // True while the item waits for the items in 'after' (never launched yet).
  isWaiting: boolean
  after: number[]
  chain: number
  itemLabel: string
  mode: 'sync' | 'async'
  // True when the last assistant turn of the child asks the user something and waits for the answer.
  awaitsAnswer: boolean
  // True when the item ended with an error.
  failed: boolean
  // True when the item ended idle without a done state, so it waits for the user.
  blocked: boolean
}

export type SplitGroup = {
  group: string
  parent: string
  parentTitle: string
  parentCwd: string
  // Earliest child start, used for the group's dated label.
  startedMs: number
  children: ChildRow[]
}

// 'mine': groups of this session (as parent or as child); 'all': the most recent groups.
export type SplitScope = 'mine' | 'all'

export type NodeKind = 'child' | 'parent'

export type PaneView = { mode: 'list' } | { mode: 'detail'; kind: NodeKind; id: string; group: string }

// count is set on collapsed activity lines that repeat; absent means one.
export type TranscriptLine = { role: 'voce' | 'claude' | 'tool'; text: string; count?: number }

// subagents: running background subagents of the viewed session.
export type TranscriptView = { id: string; available: boolean; lines: TranscriptLine[]; subagents: number }

// Detail scroll of the viewed node: rows from the bottom (0 follows the tail); max is the largest useful value.
export type DetailScroll = { id: string; rows: number; max: number }

declare module 'claude-code' {
  interface PluginState {
    'prompt-splitter': {
      delivered: Shaped<string[]>
      view: Shaped<PaneView>
      groups: Shaped<SplitGroup[]>
      scope: Shaped<SplitScope>
      transcript: Shaped<TranscriptView>
      detailOffset: Shaped<DetailScroll>
    }
  }
}
