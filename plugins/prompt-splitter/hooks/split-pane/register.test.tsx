import { expect, test } from 'claude-code/testing'

import {
  activityLabel,
  activityText,
  buildRows,
  childLabel,
  awaitsAnswer,
  childStatusText,
  colorsOf,
  colorKeyOf,
  DONE_MARK,
  isComplete,
  markOf,
  PENDING_MARK,
  collapseActivity,
  deliveryText,
  groupLabel,
  isStale,
  isUnfinished,
  isSelfView,
  parseDelivered,
  inCwd,
  parseRecords,
  rainbowColor,
  RAINBOW,
  rowColor,
  readyGroups,
  routeTarget,
  routingTitle,
  selectGroups,
  sessionTitle,
  statusText,
  subagentsText,
  tailWindow,
  transcriptLines,
  treeText,
  type ChildRow,
  type LiveAgent,
} from './register'
import type { PaneView, SplitGroup } from '../../types'

const PARENT = 'parent-session'
const LINES = [
  '{"id":"old","name":"split-old","cwd":"/w/o","started":"2026-10-01T00:00:00Z"}',
  '{"id":"c1","name":"split-alpha","cwd":"/w/a","started":"2026-10-24T10:00:00Z","parent":"parent-session","group":"g1"}',
  '{"id":"c2","name":"split-beta","cwd":"/w/b","started":"2026-10-24T10:00:00Z","parent":"parent-session","group":"g1"}',
  '{"id":"x1","name":"split-other","cwd":"/w/x","started":"2026-10-24T10:00:00Z","parent":"someone-else","group":"g9"}',
].join('\n')

// Records start at 2026-10-24T10:00:00Z; NOW is shortly after, so their live state decides.
const NOW = Date.parse('2026-10-24T10:00:30Z')

const ENDED: LiveAgent[] = [
  { id: 'c1', sessionId: 's1', status: 'idle', state: 'done' },
  { id: 'c2', sessionId: 's2', status: 'idle', state: 'done' },
]
const ONE_RUNNING: LiveAgent[] = [
  { id: 'c1', sessionId: 's1', status: 'busy', state: 'working' },
  { id: 'c2', sessionId: 's2', status: 'idle', state: 'done' },
]

test('a group whose children have all ended is ready once, then delivered', () => {
  const rows = buildRows(parseRecords(LINES), ENDED, PARENT, NOW)
  const first = readyGroups(rows, [])
  expect(first).toEqual(['g1'])

  // After the group id is stored as delivered, a later poll has nothing to send.
  expect(readyGroups(rows, [...first])).toEqual([])

  const text = deliveryText('g1', [
    { name: 'split-alpha', reply: 'resposta final' },
    { name: 'split-beta' },
  ])
  expect(text).toContain('Resultados do split (grupo g1):')
  expect(text).toContain('### split-alpha\nresposta final')
  expect(text).toContain('### split-beta\n(sem resposta final)')
  expect(text.endsWith('Revise os resultados acima e responda ao usuario com o resumo.')).toBe(true)
})

test('a group with an idle blocked child is ready, unless that child asks the user', () => {
  const blocked = { ...childRow('k1', 'k1'), group: 'gb', isRunning: false, blocked: true }
  expect(readyGroups([blocked], [])).toEqual(['gb'])
  expect(readyGroups([{ ...blocked, awaitsAnswer: true }], [])).toEqual([])
  expect(readyGroups([{ ...blocked, blocked: false, failed: true }], [])).toEqual(['gb'])
})

test('a group with a running child is not ready', () => {
  const rows = buildRows(parseRecords(LINES), ONE_RUNNING, PARENT, NOW)
  expect(readyGroups(rows, [])).toEqual([])
})

test('the pane lists only the children whose parent is this session', () => {
  const rows = buildRows(parseRecords(LINES), ONE_RUNNING, PARENT, NOW)
  expect(rows.map(r => r.name)).toEqual(['split-alpha', 'split-beta'])
  expect(rows.every(r => r.group === 'g1')).toBe(true)
  // A record missing from the live list counts as ended.
  const late = Date.parse('2026-10-24T10:05:00Z')
  const missing = buildRows(parseRecords(LINES), [], PARENT, late)
  expect(missing.every(r => !r.isRunning)).toBe(true)
})

test('a missing child inside the grace period counts as running, so its group is not ready', () => {
  const soon = Date.parse('2026-10-24T10:00:10Z')
  const rows = buildRows(parseRecords(LINES), [], PARENT, soon)
  expect(rows.every(r => r.isRunning)).toBe(true)
  expect(readyGroups(rows, [])).toEqual([])
})

test('a missing child started 5 minutes ago counts as ended', () => {
  const later = Date.parse('2026-10-24T10:05:00Z')
  const rows = buildRows(parseRecords(LINES), [], PARENT, later)
  expect(rows.every(r => !r.isRunning)).toBe(true)
  expect(readyGroups(rows, [])).toEqual(['g1'])
})

test('the live agent cwd (real path) overrides the recorded cwd when present', () => {
  const records = parseRecords('{"id":"c9","name":"split-link","cwd":"/home/x","started":"2026-10-24T10:00:00Z","parent":"parent-session","group":"g1"}')
  const live: LiveAgent[] = [{ id: 'c9', sessionId: 's9', status: 'idle', state: 'done', cwd: '/var/home/x' }]
  expect(buildRows(records, live, PARENT, NOW)[0].cwd).toBe('/var/home/x')
  expect(buildRows(records, [], PARENT, NOW)[0].cwd).toBe('/home/x')
})

test('the durable delivered file keeps only the string group ids', () => {
  expect(parseDelivered('["da097545","c885f661"]')).toEqual(['da097545', 'c885f661'])
  expect(parseDelivered('["g1", 2, null, "g2"]')).toEqual(['g1', 'g2'])
})

test('the durable delivered file yields no groups when empty, invalid or not an array', () => {
  expect(parseDelivered('')).toEqual([])
  expect(parseDelivered('{not json')).toEqual([])
  expect(parseDelivered('{"g1": true}')).toEqual([])
})

test('the status line counts running and ended children', () => {
  const rows = buildRows(parseRecords(LINES), ONE_RUNNING, PARENT, NOW)
  expect(statusText(rows)).toBe('Splits: 1 rodando, 1 encerradas (/splits abre o painel)')
  expect(statusText(buildRows(parseRecords(LINES), ENDED, PARENT, NOW))).toBe(
    'Splits: 0 rodando, 2 encerradas (/splits abre o painel)',
  )
})

const TREE = [
  '{"id":"p1","name":"split-p1","cwd":"/w/p","started":"2026-10-24T09:00:00Z","parent":"me","group":"ga","index":1,"total":2,"parent_cwd":"/w/p"}',
  '{"id":"p2","name":"split-p2","cwd":"/w/p","started":"2026-10-24T09:00:01Z","parent":"me","group":"ga","index":2,"total":2,"parent_cwd":"/w/p"}',
  '{"id":"k1","name":"split-k1","cwd":"/w/k","started":"2026-10-24T08:00:00Z","parent":"boss","group":"gb","index":1,"total":1,"parent_cwd":"/w/boss"}',
  '{"id":"z1","name":"split-z1","cwd":"/w/z","started":"2026-10-24T07:00:00Z","parent":"other","group":"gz"}',
].join('\n')

test('mine as parent keeps the groups this session dispatched', () => {
  const groups = selectGroups(parseRecords(TREE), ENDED, 'me', 'mine', NOW)
  expect(groups.map(g => g.group)).toEqual(['ga'])
  expect(groups[0].parent).toBe('me')
  expect(groups[0].children.map(c => c.index)).toEqual([1, 2])
})

test('mine as child keeps the group where this session is one of the children', () => {
  const records = parseRecords(TREE + '\n{"id":"self1234","name":"split-self","cwd":"/w/s","started":"2026-10-24T08:30:00Z","parent":"boss","group":"gb","index":2,"total":2,"parent_cwd":"/w/boss"}')
  const groups = selectGroups(records, ENDED, 'self1234abcd', 'mine', NOW)
  expect(groups.map(g => g.group)).toEqual(['gb'])
  expect(groups[0].children.map(c => c.id)).toEqual(['k1', 'self1234'])
})

test('all shows the most recent groups, limited to 10', () => {
  const many = Array.from({ length: 12 }, (_, i) =>
    `{"id":"n${i}","name":"split-n${i}","cwd":"/w","started":"2026-10-24T0${i % 10}:00:00Z","parent":"p${i}","group":"gn${i}"}`,
  ).join('\n')
  const groups = selectGroups(parseRecords(many), [], 'me', 'all', NOW)
  expect(groups.length).toBe(10)
})

test('treeText draws connectors and labels children, with the parent title and dated group first', () => {
  const groups = selectGroups(parseRecords(TREE), ENDED, 'me', 'mine', NOW).map(g => ({ ...g, parentTitle: 'Meu split' }))
  const text = treeText(groups)
  expect(text.split('\n')[0]).toBe(`Meu split  (${groupLabel(Date.parse('2026-10-24T09:00:00Z'), 2)})`)
  expect(text).toContain('├──► ✓ 1 p1  ')
  expect(text).toContain('└──► ✓ 2 p2  ')
})

test('treeText uses the title of a child when it has one', () => {
  const titled = parseRecords(
    '{"id":"t1","name":"split-t1","cwd":"/w","started":"2026-10-24T09:00:00Z","parent":"me","group":"gt","index":1,"total":1,"title":"Revisar login"}',
  )
  const groups = selectGroups(titled, [], 'me', 'mine', NOW).map(g => ({ ...g, parentTitle: 'Sessao X' }))
  expect(treeText(groups)).toContain('└──► ✓ 1 Revisar login  encerrada')
})

test('childLabel prefers the trimmed title', () => {
  expect(childLabel({ title: '  Corrigir testes  ', prompt_head: 'outro', name: 'split-x' })).toBe('Corrigir testes')
})

test('childLabel clips a long prompt_head to 60 characters with an ellipsis', () => {
  const head = 'a'.repeat(70)
  expect(childLabel({ prompt_head: head, name: 'split-x' })).toBe(`${'a'.repeat(60)}...`)
  expect(childLabel({ prompt_head: 'curto', name: 'split-x' })).toBe('curto')
})

test('childLabel falls back to the display name when there is no title or prompt', () => {
  expect(childLabel({ title: '   ', prompt_head: '', name: 'split-alpha' })).toBe('alpha')
  expect(childLabel({ name: 'split-beta' })).toBe('beta')
})

test('groupLabel formats the local date, time and count with zero padding', () => {
  const at = new Date(2026, 0, 5, 7, 4).getTime()
  expect(groupLabel(at, 3)).toBe('05/01 07:04, 3 itens')
})

test('treeText numbers records without index by start order', () => {
  const legacy = [
    '{"id":"a1","name":"split-a","cwd":"/w","started":"2026-10-24T10:00:00Z","parent":"me","group":"gl"}',
    '{"id":"a2","name":"split-b","cwd":"/w","started":"2026-10-24T10:00:05Z","parent":"me","group":"gl"}',
  ].join('\n')
  const groups = selectGroups(parseRecords(legacy), [], 'me', 'mine', NOW)
  expect(groups[0].children.map(c => c.index)).toEqual([1, 2])
  expect(groups[0].children.map(c => c.total)).toEqual([2, 2])
  expect(treeText([])).toBe('Nenhum split registrado.')
})

test('sessionTitle prefers the last custom title over the last ai title', () => {
  const text = [
    '{"type":"ai-title","aiTitle":"Titulo IA"}',
    '{"type":"custom-title","customTitle":"Meu nome"}',
    '{"type":"custom-title","customTitle":"Nome final"}',
    '{"type":"ai-title","aiTitle":"Outro titulo IA"}',
  ].join('\n')
  expect(sessionTitle(text, 'abcdef1234')).toBe('Nome final')
})

test('sessionTitle uses the ai title alone, then falls back to a short id', () => {
  expect(sessionTitle('{"type":"ai-title","aiTitle":"So IA"}', 'abcdef1234')).toBe('So IA')
  expect(sessionTitle('', 'abcdef1234')).toBe('Sessao abcdef12')
  expect(sessionTitle('not json title', 'abcdef1234')).toBe('Sessao abcdef12')
})

test('activityLabel maps tools to pt-BR labels and shows unknown names', () => {
  expect(activityLabel('Bash')).toBe('Utilizando ferramentas do terminal')
  expect(activityLabel('Read')).toBe('Lendo arquivos')
  expect(activityLabel('Grep')).toBe('Lendo arquivos')
  expect(activityLabel('Glob')).toBe('Lendo arquivos')
  expect(activityLabel('Edit')).toBe('Editando arquivos')
  expect(activityLabel('Write')).toBe('Editando arquivos')
  expect(activityLabel('NotebookEdit')).toBe('Editando arquivos')
  expect(activityLabel('Agent')).toBe('Delegando a um subagent')
  expect(activityLabel('WebSearch')).toBe('Pesquisando na web')
  expect(activityLabel('WebFetch')).toBe('Pesquisando na web')
  expect(activityLabel('Foo')).toBe('Utilizando Foo')
  expect(activityLabel('constructor')).toBe('Utilizando constructor')
})

test('collapseActivity merges consecutive equal activity lines with a count', () => {
  const lines = [
    { role: 'tool' as const, text: 'A' },
    { role: 'tool' as const, text: 'A' },
    { role: 'voce' as const, text: 'oi' },
    { role: 'tool' as const, text: 'A' },
  ]
  expect(collapseActivity(lines)).toEqual([
    { role: 'tool', text: 'A', count: 2 },
    { role: 'voce', text: 'oi' },
    { role: 'tool', text: 'A' },
  ])
  expect(activityText({ role: 'tool', text: 'Lendo arquivos', count: 6 })).toBe('Lendo arquivos (x6)')
  expect(activityText({ role: 'tool', text: 'Lendo arquivos' })).toBe('Lendo arquivos')
})

test('transcriptLines shows activity labels collapsed before the tail', () => {
  const bash = JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Bash' }] } })
  const text = JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'pronto' }] } })
  const lines = transcriptLines([bash, bash, bash, text].join('\n')).slice(-10)
  expect(lines).toEqual([
    { role: 'tool', text: 'Utilizando ferramentas do terminal', count: 3 },
    { role: 'claude', text: 'pronto' },
  ])
})

test('subagentsText uses singular for one and plural otherwise', () => {
  expect(subagentsText(1)).toBe('[1 subagent rodando de fundo]')
  expect(subagentsText(2)).toBe('[2 subagents rodando de fundo]')
  expect(subagentsText(5)).toBe('[5 subagents rodando de fundo]')
})

test('isUnfinished reads the finished flag of a subagent meta file', () => {
  expect(isUnfinished('{"agentType":"x","finished":true}')).toBe(false)
  expect(isUnfinished('{"agentType":"x","requestShape":"background"}')).toBe(true)
  expect(isUnfinished('not json')).toBe(false)
})

test('isStale applies the 15 minute window', () => {
  const now = 1_000_000_000
  expect(isStale(now - 16 * 60_000, now)).toBe(true)
  expect(isStale(now - 5 * 60_000, now)).toBe(false)
})

const ME = 'abcdef12-0000-0000-0000-000000000000'
const PARENT_ID = 'parent-session'
function childRow(id: string, sessionId: string): ChildRow {
  return {
    id,
    sessionId,
    name: `split-${id}`,
    label: `Item ${id}`,
    group: 'g1',
    cwd: '/w',
    startedMs: 0,
    isRunning: true,
    index: 1,
    total: 2,
    parent: PARENT_ID,
    isWaiting: false,
    after: [],
    chain: 1,
    itemLabel: '1',
    mode: 'async',
    awaitsAnswer: false,
    failed: false,
    blocked: false,
  }
}
const GROUPS: SplitGroup[] = [
  {
    group: 'g1',
    parent: PARENT_ID,
    parentTitle: 'Pai',
    parentCwd: '/w',
    startedMs: 0,
    children: [childRow('c1', 'c1-full'), childRow('abcdef12', ME)],
  },
]
const LIVE = new Map([['c1', 'c1-full']])
const parentView: PaneView = { mode: 'detail', kind: 'parent', id: PARENT_ID, group: 'g1' }
const childView = (id: string): PaneView => ({ mode: 'detail', kind: 'child', id, group: 'g1' })

test('routeTarget routes list, parent, live child, unknown child and self views', () => {
  expect(routeTarget({ mode: 'list' }, GROUPS, ME, LIVE)).toBeUndefined()
  expect(routeTarget(parentView, GROUPS, ME, LIVE)).toBe(PARENT_ID)
  expect(routeTarget(parentView, GROUPS, PARENT_ID, LIVE)).toBeUndefined()
  expect(routeTarget(childView('c1'), GROUPS, ME, LIVE)).toBe('c1-full')
  expect(routeTarget(childView('c1'), GROUPS, ME, new Map())).toBeUndefined()
  expect(routeTarget(childView('abcdef12'), GROUPS, ME, LIVE)).toBeUndefined()
})

test('self views are detected and have no routing title', () => {
  expect(isSelfView(childView('abcdef12'), GROUPS, ME)).toBe(true)
  expect(isSelfView(childView('c1'), GROUPS, ME)).toBe(false)
  expect(isSelfView(parentView, GROUPS, PARENT_ID)).toBe(true)
  expect(routingTitle(childView('abcdef12'), GROUPS, ME)).toBeUndefined()
  expect(routingTitle(childView('c1'), GROUPS, ME)).toBe('Item c1')
  expect(routingTitle(parentView, GROUPS, ME)).toBe('Pai')
})

test('inCwd matches the directory itself and paths under it, not sibling prefixes', () => {
  expect(inCwd('/a/sun', '/a/sun')).toBe(true)
  expect(inCwd('/a/sun/sub', '/a/sun')).toBe(true)
  expect(inCwd('/a/sunlit', '/a/sun')).toBe(false)
  expect(inCwd('/a/other', '/a/sun')).toBe(false)
  expect(inCwd('', '/a/sun')).toBe(false)
})

test('inCwd ignores a trailing slash and treats /var/home and /home as the same', () => {
  expect(inCwd('/a/sun/', '/a/sun')).toBe(true)
  expect(inCwd('/var/home/Orgo/p', '/home/Orgo/p')).toBe(true)
  expect(inCwd('/home/Orgo/p/x', '/var/home/Orgo/p')).toBe(true)
  expect(inCwd('/home/Orgo/pp', '/var/home/Orgo/p')).toBe(false)
})

test('a repeated (group, index) keeps the last record and children are sorted by index', () => {
  const records = parseRecords([
    '{"id":"c2","name":"s2","cwd":"/w","started":1000,"parent":"me","group":"g","index":2,"total":2,"title":"Dois"}',
    '{"id":"c1old","name":"s1","cwd":"/w","started":1000,"parent":"me","group":"g","index":1,"total":2,"title":"Um"}',
    '{"id":"c1new","name":"s1","cwd":"/w","started":2000,"parent":"me","group":"g","index":1,"total":2,"title":"Um"}',
  ].join('\n'))
  const rows = buildRows(records, [], 'me', NOW)
  expect(rows.map(r => r.id)).toEqual(['c1new', 'c2'])
})

test('a waiting child is not running and keeps its group from being delivered', () => {
  const records = parseRecords([
    `{"id":"wait-g-2","name":"s2","cwd":"/w","started":${NOW - 600_000},"parent":"me","group":"g","index":2,"total":2,"state":"waiting","after":[1],"title":"Dois"}`,
    `{"id":"c1","name":"s1","cwd":"/w","started":${NOW - 600_000},"parent":"me","group":"g","index":1,"total":2,"title":"Um"}`,
  ].join('\n'))
  const rows = buildRows(records, [], 'me', NOW)
  expect(rows.find(r => r.index === 2)?.isWaiting).toBe(true)
  expect(rows.find(r => r.index === 2)?.isRunning).toBe(false)
  expect(readyGroups(rows.filter(r => r.index === 1), [])).toEqual(['g'])
  expect(readyGroups(rows, [])).toEqual([])
  expect(statusText(rows)).toBe('Splits: 0 rodando, 1 aguardando, 1 encerradas (/splits abre o painel)')
})

test('treeText lists waiting items with their dependencies and never writes "de"', () => {
  const records = parseRecords([
    `{"id":"wait-g-2","name":"s2","cwd":"/w","started":${NOW - 600_000},"parent":"me","group":"g","index":2,"total":2,"state":"waiting","after":[1],"title":"Dois"}`,
    `{"id":"c1","name":"s1","cwd":"/w","started":${NOW - 600_000},"parent":"me","group":"g","index":1,"total":2,"title":"Um"}`,
  ].join('\n'))
  const groups = selectGroups(records, [], 'me', 'mine', NOW).map(g => ({ ...g, parentTitle: 'Meu split' }))
  const text = treeText(groups)
  expect(text).toContain('└──► ○ 2 Dois  aguardando Um')
  expect(text).not.toMatch(/\bde\b/)
})

test('rainbowColor gives distinct colors in rainbow order and cycles after the palette', () => {
  const first = Array.from({ length: RAINBOW.length }, (_, i) => rainbowColor(i))
  expect(first).toEqual(RAINBOW)
  expect(new Set(first).size).toBe(RAINBOW.length)
  expect(rainbowColor(RAINBOW.length)).toBe(RAINBOW[0])
})

test('tailWindow shows every item when the transcript fits', () => {
  const w = tailWindow(['a', 'b'], 5, 20, 0)
  expect(w).toEqual({ first: 0, end: 2, offset: 0, maxOffset: 0 })
})

test('tailWindow shows the end of an overflowing transcript', () => {
  const w = tailWindow(['1', '2', '3', '4', '5'], 3, 20, 0)
  expect(w.first).toBe(2)
  expect(w.end).toBe(5)
  expect(w.maxOffset).toBe(2)
})

test('tailWindow counts a long line as several wrapped rows', () => {
  // 25 chars at 10 columns take 3 rows; a 4-row window keeps the wrapped item and the last one.
  const w = tailWindow(['a', 'x'.repeat(25), 'b'], 4, 10, 0)
  expect(w.first).toBe(1)
  expect(w.end).toBe(3)
})

test('tailWindow counts each newline as a row and clamps the offset', () => {
  const w = tailWindow(['Voce\nola\n'], 3, 20, 0)
  expect(w.maxOffset).toBe(0)
  const up = tailWindow(['1', '2', '3', '4', '5'], 3, 20, 99)
  expect(up.offset).toBe(2)
  expect(up.first).toBe(0)
  expect(up.end).toBe(3)
  const down = tailWindow(['1', '2', '3', '4', '5'], 3, 20, -4)
  expect(down.offset).toBe(0)
})

test('tailWindow keeps an item taller than the window instead of showing nothing', () => {
  const w = tailWindow(['a', 'x'.repeat(100)], 3, 10, 0)
  expect(w.first).toBe(1)
  expect(w.end).toBe(2)
})

const CHAIN = [
  '{"id":"a1","name":"split-a1","cwd":"/w","started":"2026-10-24T09:00:00Z","parent":"me","group":"gc","index":1,"total":3,"chain":1,"step":1,"chain_len":2,"label":"1.1","mode":"async","title":"Primeiro"}',
  '{"id":"a2","name":"split-a2","cwd":"/w","started":"2026-10-24T09:00:01Z","parent":"me","group":"gc","index":2,"total":3,"chain":1,"step":2,"chain_len":2,"label":"1.2","mode":"sync","state":"waiting","after":[1],"title":"Segundo"}',
  '{"id":"b1","name":"split-b1","cwd":"/w","started":"2026-10-24T09:00:02Z","parent":"me","group":"gc","index":3,"total":3,"chain":2,"step":1,"chain_len":1,"label":"2.1","mode":"async","title":"Terceiro"}',
  '{"id":"d1","name":"split-d1","cwd":"/w","started":"2026-10-24T09:00:03Z","parent":"boss","group":"gd","index":1,"total":1,"chain":1,"step":1,"chain_len":1,"label":"1.1","mode":"async","title":"Outro"}',
].join('\n')

test('markOf shows done for a finished item and pending while it runs or waits', () => {
  const [done] = buildRows(parseRecords(CHAIN).filter(r => r.id === 'a1'), [], 'me', NOW)
  expect(DONE_MARK).toBe('✓')
  expect(PENDING_MARK).toBe('○')
  expect(markOf(done)).toBe('✓')
  expect(markOf({ ...done, isRunning: true })).toBe('○')
})

function ended(overrides: Partial<ChildRow>): ChildRow {
  return { ...childRow('x', 'x'), isRunning: false, ...overrides }
}

test('isComplete: busy, asking or failed is not complete, idle blocked is complete', () => {
  expect(isComplete(childRow('x', 'x'))).toBe(false)
  expect(isComplete(ended({ blocked: true }))).toBe(true)
  expect(isComplete(ended({ blocked: true, awaitsAnswer: true }))).toBe(false)
  expect(isComplete(ended({ failed: true }))).toBe(false)
  expect(isComplete(ended({ isWaiting: true }))).toBe(false)
  expect(isComplete(ended({}))).toBe(true)
})

test('awaitsAnswer is true only while the last assistant tool call has no result', () => {
  const asking = [
    '{"type":"user","message":{"content":"go"}}',
    '{"type":"assistant","message":{"content":[{"type":"text","text":"Qual?"},{"type":"tool_use","id":"t1","name":"AskUserQuestion","input":{}}]}}',
  ].join('\n')
  const answered = asking + '\n' + '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"ok"}]}}'
  const plain = '{"type":"assistant","message":{"content":[{"type":"text","text":"Pronto."}]}}'
  expect(awaitsAnswer(asking)).toBe(true)
  expect(awaitsAnswer(answered)).toBe(false)
  expect(awaitsAnswer(plain)).toBe(false)
  expect(awaitsAnswer('')).toBe(false)
})

test('buildRows carries the chain fields of the records', () => {
  const rows = buildRows(parseRecords(CHAIN), [], 'me', NOW)
  const a2 = rows.find(r => r.id === 'a2')
  expect(a2?.chain).toBe(1)
  expect(a2?.itemLabel).toBe('1.2')
  expect(a2?.mode).toBe('sync')
  expect(rows.find(r => r.id === 'b1')?.chain).toBe(2)
})

test('buildRows falls back to one chain per item for records without chain fields', () => {
  const legacy = [
    '{"id":"l1","name":"split-l1","cwd":"/w","started":"2026-10-24T10:00:00Z","parent":"me","group":"gl","index":1,"total":2}',
    '{"id":"l2","name":"split-l2","cwd":"/w","started":"2026-10-24T10:00:01Z","parent":"me","group":"gl","index":2,"total":2,"state":"waiting","after":[1]}',
  ].join('\n')
  const rows = buildRows(parseRecords(legacy), [], 'me', NOW)
  expect(rows.map(r => [r.chain, r.itemLabel, r.mode])).toEqual([
    [1, '1', 'async'],
    [2, '2', 'sync'],
  ])
})

test('colorsOf colors async items and parents by position, and leaves only waiting items without a color', () => {
  const groups = selectGroups(parseRecords(CHAIN), [], 'me', 'all', NOW)
  const colors = colorsOf(groups, 'me')
  expect(colors.get('a1')).toBeDefined()
  expect(colors.has('a2')).toBe(false)
  expect(colors.get('b1')).not.toBe(colors.get('a1'))
  expect(colors.get('d1')).not.toBe(colors.get('b1'))
  expect(colors.get('boss')).not.toBe(colors.get('a1'))
  expect(colors.has('me')).toBe(false)
})

test('colorsOf gives a started sync item its chain color instead of gray', () => {
  const records = parseRecords(CHAIN).map(r => (r.id === 'a2' ? { ...r, state: undefined } : r))
  const groups = selectGroups(records, [], 'me', 'all', NOW)
  const colors = colorsOf(groups, 'me')
  const row = groups.flatMap(g => g.children).find(c => c.id === 'a2')!
  expect(row.isWaiting).toBe(false)
  const key = colorKeyOf(row)
  expect(key).toBe('chain:gc:1')
  expect(colors.get(key)).toBeDefined()
  expect(colors.get(key)).not.toBe('gray')
  expect(rowColor(row, colors)).toBe(colors.get(key))
})

test('rowColor shows gray only for an item that did not start yet', () => {
  const groups = selectGroups(parseRecords(CHAIN), [], 'me', 'all', NOW)
  const colors = colorsOf(groups, 'me')
  const waiting = groups.flatMap(g => g.children).find(c => c.id === 'a2')!
  const running = groups.flatMap(g => g.children).find(c => c.id === 'a1')!
  expect(rowColor(waiting, colors)).toBe('gray')
  expect(rowColor(running, colors)).not.toBe('gray')
})

test('treeText marks every item with its arrow and label and ends with the legend', () => {
  const groups = selectGroups(parseRecords(CHAIN), [], 'me', 'all', NOW).map(g => ({ ...g, parentTitle: 'Meu split' }))
  const text = treeText(groups)
  expect(text).toContain('├──► ✓ 1.1 Primeiro  ')
  expect(text).toContain('├──► ○ 1.2 Segundo  aguardando Primeiro')
  expect(text.endsWith('✓ completo   ○ em andamento ou aguardando')).toBe(true)
})

test('childStatusText shows the pending mark and the item label', () => {
  const [row] = buildRows(parseRecords(CHAIN).filter(r => r.id === 'a2'), [], 'me', NOW)
  expect(childStatusText(row, 'Meu split')).toBe('Split: item ○ 1.2  Meu split  (/splits)')
})
