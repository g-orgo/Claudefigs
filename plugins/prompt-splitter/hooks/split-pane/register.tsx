// Split pane of the prompt-splitter plugin: shows the split groups as a tree, opens windows and delivers final replies.

import { atom, read, update } from 'claude-code'
import type { Hook, Register } from 'claude-code'

import type {
  ChildRow,
  DetailScroll,
  NodeKind,
  PaneView,
  SplitGroup,
  SplitRecord,
  SplitScope,
  TranscriptLine,
  TranscriptView,
} from '../../types'

type Dollar = Parameters<Hook<'session.start'>>[0]

const PANE = 'split-sessions'
const POLL_MS = 3000
const TAIL = 30
const CLIP = 300
const PREFIX = 'split-'
const ALL_LIMIT = 10
const TITLE_MS = 60_000
const LABEL_MAX = 60
// Status marks: a complete item is done, a pending one is still running or waiting.
export const DONE_MARK = '✓'
export const PENDING_MARK = '○'
const LEGEND = `${DONE_MARK} completo   ${PENDING_MARK} em andamento ou aguardando`
const MISS_MS = 5 * 60_000
const CLOSING = 'Revise os resultados acima e responda ao usuario com o resumo.'
// A running subagent whose files were not touched this long is taken as killed.
const STALE_MS = 15 * 60_000
// `claude split` (scripts/claude-split.sh) sets CLAUDE_SPLIT_VIEWER=1: the session is a read-only, full-screen viewer.
// Rows asked for the inline pane in viewer mode; the engine caps it at what the layout spares, so it fills the screen.
export const VIEWER_ROWS = 500
// Commands the viewer still runs; every other submission is dropped.
export const VIEWER_COMMANDS = ['splits', 'prompt-splitter:sessions', 'exit', 'quit']
export const VIEWER_DROP = 'Visor somente leitura: nada e enviado desta sessao (Ctrl+C sai).'

// In viewer mode, the drop reason for a submission, or undefined when it may run (an allowed command).
export function viewerDrop(e: { command?: { name: string } }): string | undefined {
  return e.command !== undefined && VIEWER_COMMANDS.includes(e.command.name) ? undefined : VIEWER_DROP
}

// Each atom's tag is bumped when its shape changes, so old stored values are declined.
const delivered = atom({ plugin: 'prompt-splitter', key: 'delivered' } as const, [] as string[], {
  shape: 'delivered-1',
})
const view = atom({ plugin: 'prompt-splitter', key: 'view' } as const, { mode: 'list' } as PaneView, {
  shape: 'view-2',
})
const groupsAtom = atom({ plugin: 'prompt-splitter', key: 'groups' } as const, [] as SplitGroup[], {
  shape: 'groups-1',
})
const scopeAtom = atom({ plugin: 'prompt-splitter', key: 'scope' } as const, 'mine' as SplitScope, {
  shape: 'scope-1',
})
const transcript = atom(
  { plugin: 'prompt-splitter', key: 'transcript' } as const,
  { id: '', available: false, lines: [], subagents: 0 } as TranscriptView,
  { shape: 'transcript-3' },
)

// Rows the detail transcript scrolls by, per viewed node; the render keeps rows and max in step with the window.
const detailOffset = atom(
  { plugin: 'prompt-splitter', key: 'detailOffset' } as const,
  { id: '', rows: 0, max: 0 } as DetailScroll,
  { shape: 'detail-scroll-1' },
)

// Process-local guards: the pane opens once, and a group is never delivered twice at once.
let opened = false
// Whether the pane is currently placed; the unasked open can be refused at narrow widths.
let placed = false
const inFlight = new Set<string>()
// The detail window's last drawn layout: the node shown and how far its transcript can scroll up.
let layout = { id: '', max: 0 }
// Parent titles per parent session, re-read at most once per TITLE_MS (transcripts can be many MB).
const titleCache = new Map<string, { at: number; title: string }>()
// Parent transcript paths found by listing the projects folder; an empty path is a remembered miss.
const transcriptCache = new Map<string, { at: number; path: string }>()
// Full session ids of the live agents, by their 8-char id; refreshed by each poll and read by prompt routing.
let liveIds = new Map<string, string>()
// True in a `claude split` session; read from CLAUDE_SPLIT_VIEWER at session.start.
let viewer = false

export type LiveAgent = {
  id: string
  sessionId?: string
  status?: string
  state?: string
  cwd?: string
}

type Entry = {
  type?: unknown
  isMeta?: unknown
  isCompactSummary?: unknown
  message?: { content?: unknown }
  customTitle?: unknown
  aiTitle?: unknown
}
type Block = { kind: 'text'; text: string } | { kind: 'tool'; name: string }

export function slugFor(cwd: string): string {
  return cwd.replace(/[^A-Za-z0-9]/g, '-')
}

export function displayName(name: string): string {
  return name.startsWith(PREFIX) ? name.slice(PREFIX.length) : name
}

// The descriptive name of a child: its title, else its clipped prompt, else its display name.
export function childLabel(record: Pick<SplitRecord, 'title' | 'prompt_head' | 'name'>): string {
  const title = record.title?.trim()
  if (title) return title
  const head = record.prompt_head?.trim()
  if (head) return head.length > LABEL_MAX ? `${head.slice(0, LABEL_MAX)}...` : head
  return displayName(record.name)
}

// The dated label of a group, in local time: "dd/mm HH:MM, N itens".
export function groupLabel(startedMs: number, count: number): string {
  const d = new Date(startedMs)
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}, ${count} itens`
}

function clip(text: string): string {
  return text.replace(/\s+/g, ' ').slice(0, CLIP)
}

function toMs(value: string | number): number {
  if (typeof value === 'number') return value
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

export function ageLabel(ms: number): string {
  const minutes = Math.max(0, Math.floor(ms / 60000))
  if (minutes < 1) return '<1m'
  if (minutes < 60) return `${minutes}m`
  return `${Math.floor(minutes / 60)}h`
}

function isSplitRecord(value: unknown): value is SplitRecord {
  if (typeof value !== 'object' || value === null) return false
  const r = value as Partial<Record<keyof SplitRecord, unknown>>
  return (
    typeof r.id === 'string' &&
    typeof r.name === 'string' &&
    typeof r.cwd === 'string' &&
    typeof r.parent === 'string' &&
    typeof r.group === 'string' &&
    (typeof r.started === 'string' || typeof r.started === 'number')
  )
}

// Lines without the required fields are skipped; the optional fields are kept when present.
export function parseRecords(text: string): SplitRecord[] {
  const out: SplitRecord[] = []
  for (const line of text.split('\n')) {
    if (line.trim() === '') continue
    let value: unknown
    try {
      value = JSON.parse(line)
    } catch {
      continue
    }
    if (isSplitRecord(value)) out.push(value)
  }
  return out
}

// A just-dispatched child may not be in the live list yet, so a missing record
// counts as running for this long after its start time, then as ended.
export const MISSING_GRACE_MS = 90_000

// A live record is running when busy or working; a missing one is running only inside the grace period.
export function isRunning(live: LiveAgent | undefined, startedMs: number, now: number): boolean {
  if (live !== undefined) return live.status === 'busy' || live.state === 'working'
  return now - startedMs < MISSING_GRACE_MS
}

// True when the item is finished: not running, not waiting, and either done or failed or asking the user.
export function isComplete(child: ChildRow): boolean {
  if (child.isRunning || child.isWaiting) return false
  return !child.failed && !child.awaitsAnswer
}

// True when the last assistant turn of a transcript calls a tool that has no result yet, i.e. it waits for the user.
export function awaitsAnswer(transcriptText: string): boolean {
  const answered = new Set<string>()
  let pending: string[] = []
  for (const line of transcriptText.split('\n')) {
    const entry = parseEntry(line)
    const content = entry?.message?.content
    if (!Array.isArray(content)) continue
    if (entry?.type === 'assistant') {
      pending = content.flatMap(b => {
        const block = b as { type?: unknown; id?: unknown }
        return block.type === 'tool_use' && typeof block.id === 'string' ? [block.id] : []
      })
    } else if (entry?.type === 'user') {
      for (const b of content) {
        const block = b as { type?: unknown; tool_use_id?: unknown }
        if (block.type === 'tool_result' && typeof block.tool_use_id === 'string') answered.add(block.tool_use_id)
      }
    }
  }
  return pending.some(id => !answered.has(id))
}

// True when the child row is the session this plugin runs in (its sessionId or its 8-char id).
export function isSelfChild(child: ChildRow, me: string): boolean {
  return child.sessionId === me || child.id === me.slice(0, 8)
}

// True when the detail view points at the session this plugin runs in; such a view is shown as the list.
export function isSelfView(view: PaneView, groups: SplitGroup[], me: string): boolean {
  if (view.mode !== 'detail') return false
  const group = groups.find(g => g.group === view.group)
  if (!group) return false
  if (view.kind === 'parent') return group.parent === me
  const child = group.children.find(c => c.id === view.id)
  return child !== undefined && isSelfChild(child, me)
}

// The title of the node prompts are routed to, or undefined when prompts are not routed.
export function routingTitle(view: PaneView, groups: SplitGroup[], me: string): string | undefined {
  if (view.mode !== 'detail' || isSelfView(view, groups, me)) return undefined
  const group = groups.find(g => g.group === view.group)
  if (!group) return undefined
  if (view.kind === 'parent') return group.parentTitle
  return group.children.find(c => c.id === view.id)?.label
}

// The full session id that a viewed node's prompts go to, or undefined when it is not known.
export function routeTarget(
  view: PaneView,
  groups: SplitGroup[],
  me: string,
  liveIds: ReadonlyMap<string, string>,
): string | undefined {
  if (view.mode !== 'detail' || isSelfView(view, groups, me)) return undefined
  const group = groups.find(g => g.group === view.group)
  if (!group) return undefined
  if (view.kind === 'parent') return group.parent
  const child = group.children.find(c => c.id === view.id)
  return child ? liveIds.get(child.id) : undefined
}

// A route ticket: written by the sending pane right before it routes a typed prompt, so the receiving child can
// tell the person's own prompt from any other session's message (session.receive never names the sending session).
export type RouteTicket = { from: string; text: string; at: number }

export const ROUTE_TTL_MS = 120_000
// A small allowance for clocks of two processes read a moment apart.
const ROUTE_SKEW_MS = 5_000
const ROUTED_PLUGIN = 'prompt-splitter'

export function routesPath(home: string, sessionId: string): string {
  return `${home}/.claude/state/prompt-splitter-routes/${sessionId}.json`
}

function isTicket(value: unknown): value is RouteTicket {
  if (typeof value !== 'object' || value === null) return false
  const t = value as Partial<Record<keyof RouteTicket, unknown>>
  return typeof t.from === 'string' && typeof t.text === 'string' && typeof t.at === 'number'
}

export function parseTickets(text: string): RouteTicket[] {
  try {
    const value: unknown = JSON.parse(text)
    return Array.isArray(value) ? value.filter(isTicket) : []
  } catch {
    return []
  }
}

// The message body without the engine's cross-session envelope, when the text still carries it.
export function unwrapEnvelope(text: string): string {
  const match = /^\s*<cross-session-message\b[^>]*>\n?([\s\S]*?)\n?<\/cross-session-message>/.exec(text)
  return (match ? match[1] : text).trim()
}

// The parent registered for this session in the dispatch records (its last record by 8-char id), or undefined.
export function registeredParent(records: SplitRecord[], me: string): string | undefined {
  const mine = records.filter(r => r.id === me.slice(0, 8))
  const parent = mine[mine.length - 1]?.parent
  return parent === undefined || parent === '' ? undefined : parent
}

// Index of the ticket that makes a delivery the person's own prompt, or -1 to keep the default handling.
// Accepted only when the message was composed by prompt-splitter (the sender's claim) AND a fresh ticket
// from this session's registered parent carries the same text; each ticket is good for one delivery.
export function routedTicket(
  origin: { kind: string },
  text: string,
  parent: string | undefined,
  tickets: readonly RouteTicket[],
  now: number,
): number {
  const o = origin as { kind: string; plugin?: unknown; teammate?: unknown }
  if (o.kind !== 'peer' || o.plugin !== ROUTED_PLUGIN || o.teammate !== undefined) return -1
  if (parent === undefined) return -1
  const body = unwrapEnvelope(text)
  if (body === '') return -1
  return tickets.findIndex(
    t => t.from === parent && t.text.trim() === body && t.at - now <= ROUTE_SKEW_MS && now - t.at <= ROUTE_TTL_MS,
  )
}

// Records a ticket for a prompt about to be routed to `target`, dropping expired ones. Best effort.
async function addTicket($: Dollar, target: string, ticket: RouteTicket): Promise<void> {
  try {
    const path = routesPath(await homeDir($), target)
    const kept = parseTickets(await readText($, path)).filter(t => ticket.at - t.at <= ROUTE_TTL_MS)
    await $.fs.write(path, JSON.stringify([...kept, ticket]))
  } catch {
    // Without a ticket the child treats the prompt as another session's message.
  }
}

// Keeps the last record of each (group, index) slot, the one appended later; records without index are all kept.
function lastPerSlot<T extends SplitRecord>(group: T[]): T[] {
  const slots = new Map<number, T>()
  const loose: T[] = []
  for (const r of group) {
    if (r.index === undefined) loose.push(r)
    else slots.set(r.index, r)
  }
  return [...loose, ...slots.values()]
}

// Numbers and builds the child rows of any records. Records without 'index' are numbered by start order.
function rowsOf(records: SplitRecord[], live: LiveAgent[], now: number): ChildRow[] {
  const byId = new Map<string, LiveAgent>()
  for (const agent of live) byId.set(agent.id, agent)
  const members = new Map<string, SplitRecord[]>()
  for (const r of records) members.set(r.group, [...(members.get(r.group) ?? []), r])
  const out: ChildRow[] = []
  for (const group of members.values()) {
    const ordered = [...lastPerSlot(group)].sort((a, b) => toMs(a.started) - toMs(b.started))
    if (ordered.every(r => r.index !== undefined)) ordered.sort((a, b) => (a.index ?? 0) - (b.index ?? 0))
    ordered.forEach((r, position) => {
      const agent = byId.get(r.id)
      const startedMs = toMs(r.started)
      const index = r.index ?? position + 1
      const isWaiting = r.state === 'waiting'
      const running = !isWaiting && isRunning(agent, startedMs, now)
      const failed = !running && !isWaiting && agent?.state === 'failed'
      // Ended idle without a done state: the item is finished but waits for the user.
      const blocked = !running && !isWaiting && agent !== undefined && agent.state !== 'done' && !failed
      out.push({
        id: r.id,
        sessionId: agent?.sessionId ?? r.id,
        name: r.name,
        group: r.group,
        label: childLabel(r),
        cwd: agent?.cwd ?? r.cwd,
        startedMs,
        isRunning: running,
        index,
        total: r.total ?? ordered.length,
        parent: r.parent,
        isWaiting,
        after: r.after ?? [],
        // Records without a chain are each a chain of their own.
        chain: r.chain ?? index,
        itemLabel: r.label ?? String(index),
        mode: r.mode ?? (r.after && r.after.length > 0 ? 'sync' : 'async'),
        // Filled by the poll from the transcript of the ended items; false until then.
        awaitsAnswer: false,
        failed,
        blocked,
      })
    })
  }
  return out
}

export function buildRows(records: SplitRecord[], live: LiveAgent[], parent: string, now: number): ChildRow[] {
  return rowsOf(
    records.filter(r => r.parent === parent),
    live,
    now,
  )
}

// The groups shown in the pane: 'mine' keeps the groups of this session as parent or child;
// 'all' keeps the ALL_LIMIT most recent groups. Parent titles are filled in by the poll.
export function selectGroups(
  records: SplitRecord[],
  live: LiveAgent[],
  me: string,
  scope: SplitScope,
  now: number,
): SplitGroup[] {
  const withParent = records.filter(r => r.parent !== '')
  const firstOf = new Map<string, SplitRecord>()
  for (const r of withParent) if (!firstOf.has(r.group)) firstOf.set(r.group, r)
  const byGroup = new Map<string, ChildRow[]>()
  for (const row of rowsOf(withParent, live, now)) {
    byGroup.set(row.group, [...(byGroup.get(row.group) ?? []), row])
  }
  const newest = (g: SplitGroup): number => Math.max(...g.children.map(c => c.startedMs))
  const groups: SplitGroup[] = Array.from(byGroup, ([group, children]) => ({
    group,
    parent: children[0].parent,
    parentTitle: fallbackTitle(children[0].parent),
    parentCwd: firstOf.get(group)?.parent_cwd ?? '',
    startedMs: Math.min(...children.map(c => c.startedMs)),
    children,
  })).sort((a, b) => newest(b) - newest(a))
  if (scope === 'mine') {
    return groups.filter(g => g.parent === me || g.children.some(c => isSelfChild(c, me)))
  }
  return groups.slice(0, ALL_LIMIT)
}

// Normalizes a path for comparison: no trailing slash, and /var/home is the same as /home (Bazzite symlink).
function normCwd(path: string): string {
  const trimmed = path.replace(/\/+$/, '')
  if (trimmed === '') return path.startsWith('/') ? '/' : ''
  if (trimmed === '/var/home' || trimmed.startsWith('/var/home/')) return trimmed.slice(4)
  return trimmed
}

// True when the path equals the project directory or lies under it (sibling prefixes do not match).
export function inCwd(path: string, cwd: string): boolean {
  const p = normCwd(path)
  const c = normCwd(cwd)
  if (p === '' || c === '') return false
  const base = c.endsWith('/') ? c : `${c}/`
  return p === c || p.startsWith(base)
}

// A group belongs to the project when its parent or any of its children runs under the directory.
export function groupInCwd(group: SplitGroup, cwd: string): boolean {
  return inCwd(group.parentCwd, cwd) || group.children.some(c => inCwd(c.cwd, cwd))
}

// Palette of the session names in rainbow order: distinct colors until it runs out, then it cycles.
export const RAINBOW = ['#ff5f5f', '#ff8700', '#ffd700', '#87ff00', '#00d787', '#00afff', '#5f87ff', '#af5fff', '#ff5fd7']

export function rainbowColor(i: number): string {
  const n = RAINBOW.length
  return RAINBOW[((i % n) + n) % n]
}

// Key of an item in the color map: each sync chain of a group shares one key, async items use their id.
export function colorKeyOf(child: ChildRow): string {
  return child.mode === 'sync' ? `chain:${child.group}:${child.chain}` : child.id
}

// Color of each visible session node, by running position in render order (parents, then children).
// Only items that did not start yet (they depend on another process) are left without a color, so they show gray;
// this session is left without a color too. The same map colors a node's title in its detail view.
// Parents and items that already started share the counter; a sync chain takes one color for its whole run.
export function colorsOf(groups: SplitGroup[], me: string): Map<string, string> {
  const out = new Map<string, string>()
  let next = 0
  const colorFor = (key: string): void => {
    if (!out.has(key)) out.set(key, rainbowColor(next++))
  }
  for (const g of groups) {
    if (g.parent !== me) colorFor(g.parent)
    for (const c of g.children) {
      if (c.isWaiting || isSelfChild(c, me)) continue
      colorFor(colorKeyOf(c))
    }
  }
  return out
}

// Color of an item row: gray only while it did not start yet (it waits on another process), else its own color.
export function rowColor(child: ChildRow, colors: Map<string, string>): string {
  if (child.isWaiting) return 'gray'
  return colors.get(colorKeyOf(child)) ?? 'gray'
}

// Suffix of a waiting item: the labels of the items it waits on, looked up in its own group.
export function waitingText(child: ChildRow, siblings: ChildRow[]): string {
  const labels = child.after.map(i => siblings.find(k => k.index === i)?.label ?? `item ${i}`)
  return `aguardando ${labels.join(', ')}`
}

// State suffix of an item row: what it does now, or why it is not finished.
export function stateText(child: ChildRow, siblings: ChildRow[]): string {
  if (child.isWaiting) return waitingText(child, siblings)
  if (child.isRunning) return 'rodando'
  if (child.failed) return 'falhou'
  if (child.awaitsAnswer) return 'aguarda sua resposta'
  if (child.blocked) return 'concluida, aguarda voce'
  return 'encerrada'
}

// Mark of an item: done when complete, pending while it runs, waits or is blocked.
export function markOf(child: ChildRow): string {
  return isComplete(child) ? DONE_MARK : PENDING_MARK
}

// Plain-text tree of the groups, used by the slash command answer.
export function treeText(groups: SplitGroup[]): string {
  if (groups.length === 0) return 'Nenhum split registrado.'
  const tree = groups
    .map(g => {
      const lines = [`${g.parentTitle}  (${groupLabel(g.startedMs, g.children.length)})`, '│']
      g.children.forEach((c, i) => {
        const connector = i === g.children.length - 1 ? '└──►' : '├──►'
        lines.push(`${connector} ${markOf(c)} ${c.itemLabel} ${c.label}  ${stateText(c, g.children)}`)
      })
      return lines.join('\n')
    })
    .join('\n\n')
  return `${tree}\n\n${LEGEND}`
}

export function childStatusText(child: ChildRow, parentTitle: string): string {
  return `Split: item ${markOf(child)} ${child.itemLabel}  ${parentTitle}  (/splits)`
}

// Groups whose children have all ended and that were not delivered yet.
// A child no longer needs anything before delivery: complete, or failed (its error still goes to the parent).
function isSettled(child: ChildRow): boolean {
  return isComplete(child) || (child.failed && !child.isRunning && !child.isWaiting)
}

export function readyGroups(children: ChildRow[], done: readonly string[]): string[] {
  const groups = new Map<string, ChildRow[]>()
  for (const child of children) {
    groups.set(child.group, [...(groups.get(child.group) ?? []), child])
  }
  return Array.from(groups)
    .filter(([group, kids]) => !done.includes(group) && kids.every(isSettled))
    .map(([group]) => group)
}

export function fallbackTitle(id: string): string {
  return `Sessao ${id.slice(0, 8)}`
}

function parseEntry(line: string): Entry | undefined {
  if (line.trim() === '') return undefined
  try {
    const value: unknown = JSON.parse(line)
    return typeof value === 'object' && value !== null ? (value as Entry) : undefined
  } catch {
    return undefined
  }
}

// The title of a session: the last custom title, else the last AI title, else a short id.
export function sessionTitle(text: string, id: string): string {
  let custom: string | undefined
  let ai: string | undefined
  for (const line of text.split('\n')) {
    if (!line.includes('title')) continue
    const entry = parseEntry(line)
    if (entry?.type === 'custom-title' && typeof entry.customTitle === 'string' && entry.customTitle.trim() !== '') {
      custom = entry.customTitle
    }
    if (entry?.type === 'ai-title' && typeof entry.aiTitle === 'string' && entry.aiTitle.trim() !== '') {
      ai = entry.aiTitle
    }
  }
  return custom ?? ai ?? fallbackTitle(id)
}

function blocksOf(content: unknown): Block[] {
  if (typeof content === 'string') return content === '' ? [] : [{ kind: 'text', text: content }]
  if (!Array.isArray(content)) return []
  const out: Block[] = []
  for (const block of content as unknown[]) {
    if (typeof block !== 'object' || block === null) continue
    const b = block as { type?: unknown; text?: unknown; name?: unknown }
    if (b.type === 'text' && typeof b.text === 'string' && b.text !== '') {
      out.push({ kind: 'text', text: b.text })
    } else if (b.type === 'tool_use' && typeof b.name === 'string') {
      out.push({ kind: 'tool', name: b.name })
    }
  }
  return out
}

const ACTIVITY = new Map<string, string>([
  ['Bash', 'Utilizando ferramentas do terminal'],
  ['Read', 'Lendo arquivos'],
  ['Grep', 'Lendo arquivos'],
  ['Glob', 'Lendo arquivos'],
  ['Edit', 'Editando arquivos'],
  ['Write', 'Editando arquivos'],
  ['NotebookEdit', 'Editando arquivos'],
  ['Agent', 'Delegando a um subagent'],
  ['WebSearch', 'Pesquisando na web'],
  ['WebFetch', 'Pesquisando na web'],
])

// The pt-BR label of a tool call in the pane; unknown tools show their own name.
export function activityLabel(name: string): string {
  return ACTIVITY.get(name) ?? `Utilizando ${clip(name)}`
}

// The text of an activity line, with its repeat count when it stands for more than one call.
export function activityText(line: TranscriptLine): string {
  return line.count !== undefined && line.count > 1 ? `${line.text} (x${line.count})` : line.text
}

// Merges consecutive activity lines with the same label into one line with a count.
export function collapseActivity(lines: TranscriptLine[]): TranscriptLine[] {
  const out: TranscriptLine[] = []
  for (const line of lines) {
    const last = out[out.length - 1]
    if (line.role === 'tool' && last?.role === 'tool' && last.text === line.text) {
      last.count = (last.count ?? 1) + 1
    } else {
      out.push({ ...line })
    }
  }
  return out
}

// Tags the harness injects into user records; mirrors INJECTED_TAGS in scripts/office/data.py.
const INJECTED_TAGS = [
  'system-reminder',
  'task-notification',
  'agent-message',
  'cross-session-message',
  'local-command-stdout',
  'local-command-stderr',
  'local-command-caveat',
  'command-name',
  'command-message',
  'command-args',
  'tools-used-before-summary',
]
const TAG_ALTERNATION = INJECTED_TAGS.join('|')
const PAIRED_BLOCK = new RegExp(`<(${TAG_ALTERNATION})(?:\\s[^>]*)?>[\\s\\S]*?</\\1>`, 'g')
const UNTERMINATED_START = new RegExp(`^<(?:${TAG_ALTERNATION})(?:\\s[^>]*)?>`)
const ORPHAN_CLOSE = new RegExp(`^[\\s\\S]*</(?:${TAG_ALTERNATION})>`)

// Removes harness-injected tag blocks from user text: paired blocks, a cut-off opening tag at the start
// (drops the whole text), and an orphan closing tag (drops everything through its last occurrence).
export function stripInjected(text: string): string {
  let out = text.replace(PAIRED_BLOCK, '')
  if (UNTERMINATED_START.test(out.trimStart())) out = ''
  out = out.replace(ORPHAN_CLOSE, '')
  return out.trim()
}

// The last TAIL items of a transcript, as the pane shows them.
export function transcriptLines(text: string): TranscriptLine[] {
  const out: TranscriptLine[] = []
  for (const line of text.split('\n')) {
    const entry = parseEntry(line)
    if (!entry) continue
    if (entry.type === 'user' && (entry.isMeta || entry.isCompactSummary)) continue
    const role = entry.type === 'user' ? 'voce' : entry.type === 'assistant' ? 'claude' : undefined
    if (!role) continue
    for (const block of blocksOf(entry.message?.content)) {
      if (block.kind === 'tool') {
        out.push({ role: 'tool', text: activityLabel(block.name) })
        continue
      }
      const shown = role === 'voce' ? stripInjected(block.text) : block.text
      if (shown !== '') out.push({ role, text: clip(shown) })
    }
  }
  return collapseActivity(out).slice(-TAIL)
}

// Rows one item takes when wrapped at the given width: each line wraps on its own, an empty line still takes one row.
function wrappedRows(text: string, columns: number): number {
  const width = Math.max(1, columns)
  return text.split('\n').reduce((sum, part) => sum + Math.max(1, Math.ceil(part.length / width)), 0)
}

// The items that fit a window of `height` rows ending `offset` rows above the bottom of the transcript.
// Items are kept whole: only those lying entirely inside the window are picked (first..end, end exclusive).
export function tailWindow(
  items: string[],
  height: number,
  columns: number,
  offset: number,
): { first: number; end: number; offset: number; maxOffset: number } {
  const counts = items.map(text => wrappedRows(text, columns))
  const total = counts.reduce((sum, n) => sum + n, 0)
  const room = Math.max(1, height)
  const maxOffset = Math.max(0, total - room)
  const clamped = Math.min(Math.max(offset, 0), maxOffset)
  const bottom = total - clamped
  const top = bottom - room
  const picked: number[] = []
  let at = 0
  counts.forEach((n, i) => {
    if (at >= top && at + n <= bottom) picked.push(i)
    at += n
  })
  // An item taller than the window would leave it empty: the one under the window's bottom row is shown, clipped.
  if (picked.length === 0 && total > 0) {
    let start = 0
    const hit = counts.findIndex(n => (start += n) >= bottom)
    picked.push(hit === -1 ? counts.length - 1 : hit)
  }
  return {
    first: picked[0] ?? 0,
    end: picked.length > 0 ? picked[picked.length - 1] + 1 : 0,
    offset: clamped,
    maxOffset,
  }
}

// True when a subagent meta file says it is still running (no finished flag). Unreadable files count as ended.
export function isUnfinished(metaText: string): boolean {
  try {
    const value: unknown = JSON.parse(metaText)
    return typeof value === 'object' && value !== null && (value as { finished?: unknown }).finished !== true
  } catch {
    return false
  }
}

// True when a file last changed at least STALE_MS before now.
export function isStale(mtimeMs: number, now: number): boolean {
  return now - mtimeMs >= STALE_MS
}

// The status line of the running background subagents of the viewed session.
export function subagentsText(count: number): string {
  return count === 1 ? '[1 subagent rodando de fundo]' : `[${count} subagents rodando de fundo]`
}

// The text of the last assistant entry that has text.
export function finalReply(text: string): string | undefined {
  const lines = text.split('\n')
  for (let i = lines.length - 1; i >= 0; i--) {
    const entry = parseEntry(lines[i])
    if (entry?.type !== 'assistant') continue
    const parts: string[] = []
    for (const block of blocksOf(entry.message?.content)) {
      if (block.kind === 'text') parts.push(block.text)
    }
    if (parts.length > 0) return parts.join('\n')
  }
  return undefined
}

export function deliveryText(group: string, replies: { name: string; reply?: string }[]): string {
  const sections = replies.map(r => `### ${r.name}\n${r.reply ?? '(sem resposta final)'}`)
  return `Resultados do split (grupo ${group}):\n\n${sections.join('\n\n')}\n\n${CLOSING}`
}

async function homeDir($: Dollar): Promise<string> {
  return (await $.env.get('HOME')) ?? ''
}

async function readText($: Dollar, path: string): Promise<string> {
  try {
    return await $.fs.read(path)
  } catch {
    return ''
  }
}

// Throws when the list cannot be read, so no child is taken as ended by mistake.
async function readLive($: Dollar): Promise<LiveAgent[]> {
  const result = await $.process.run(['claude', 'agents', '--json', '--all'])
  if (result.exitCode !== 0) throw new Error('claude agents failed')
  const value: unknown = JSON.parse(result.stdout)
  return Array.isArray(value) ? (value as LiveAgent[]) : []
}

function childTranscriptPath(home: string, child: ChildRow): string {
  return `${home}/.claude/projects/${slugFor(child.cwd)}/${child.sessionId}.jsonl`
}

// Fills awaitsAnswer on the rows that ended, read from their transcripts; running and waiting rows are skipped.
async function fillAnswers($: Dollar, rows: ChildRow[]): Promise<void> {
  for (const row of rows) {
    // Only an idle live session can hold a pending question; done or missing ones skip the read.
    if (row.isRunning || row.isWaiting || !row.blocked) continue
    row.awaitsAnswer = awaitsAnswer(await readTranscriptText($, row))
  }
}

async function readTranscriptText($: Dollar, child: ChildRow): Promise<string> {
  return readText($, childTranscriptPath(await homeDir($), child))
}

// Background subagents of a transcript live in its sibling 'subagents' folder. Missing folder = 0.
// A subagent counts when its meta file lacks 'finished' and it was touched within STALE_MS.
async function subagentCount($: Dollar, transcriptPath: string, now: number): Promise<number> {
  if (transcriptPath === '') return 0
  const dir = `${transcriptPath.replace(/\.jsonl$/, '')}/subagents`
  let entries: { name: string; mtimeMs?: number }[] = []
  try {
    entries = await $.fs.list(dir)
  } catch {
    return 0
  }
  let count = 0
  for (const meta of entries) {
    if (!meta.name.endsWith('.meta.json')) continue
    const base = meta.name.slice(0, -'.meta.json'.length)
    const jsonl = entries.find(e => e.name === `${base}.jsonl`)
    const touched = [meta.mtimeMs, jsonl?.mtimeMs].filter((t): t is number => typeof t === 'number')
    if (touched.length > 0 && isStale(Math.max(...touched), now)) continue
    if (isUnfinished(await readText($, `${dir}/${meta.name}`))) count += 1
  }
  return count
}

// Where the parent's transcript is: the path the dispatch recorded, else the one derived from its cwd.
// Older records lack parent_transcript: the projects folder is searched once per parent (misses cached for MISS_MS).
async function parentTranscriptPath(
  $: Dollar,
  home: string,
  group: SplitGroup,
  recorded: Map<string, string>,
  now: number,
): Promise<string> {
  const known = recorded.get(group.group)
  if (known) return known
  if (group.parentCwd !== '') {
    const derived = `${home}/.claude/projects/${slugFor(group.parentCwd)}/${group.parent}.jsonl`
    if (await $.fs.exists(derived)) return derived
  }
  const hit = transcriptCache.get(group.parent)
  if (hit && (hit.path !== '' || now - hit.at < MISS_MS)) return hit.path
  const root = `${home}/.claude/projects`
  let dirs: { name: string; kind: string }[] = []
  try {
    dirs = await $.fs.list(root)
  } catch {
    dirs = []
  }
  let found = ''
  for (const dir of dirs) {
    if (dir.kind !== 'dir') continue
    const candidate = `${root}/${dir.name}/${group.parent}.jsonl`
    if (await $.fs.exists(candidate)) {
      found = candidate
      break
    }
  }
  transcriptCache.set(group.parent, { at: now, path: found })
  return found
}

async function parentTitleOf($: Dollar, parent: string, path: string, now: number): Promise<string> {
  const hit = titleCache.get(parent)
  if (hit && now - hit.at < TITLE_MS) return hit.title
  if (path === '') return fallbackTitle(parent)
  const title = sessionTitle(await readText($, path), parent)
  titleCache.set(parent, { at: now, title })
  return title
}

// Durable record of delivered groups, kept outside $.state so a reload or a worker restart cannot resend them.
export function parseDelivered(text: string): string[] {
  if (text.trim() === '') return []
  try {
    const value: unknown = JSON.parse(text)
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

// One-line status shown while the pane is not placed.
export function statusText(children: ChildRow[]): string {
  const running = children.filter(c => c.isRunning).length
  const waiting = children.filter(c => c.isWaiting).length
  const ended = children.length - running - waiting
  const parts = [`${running} rodando`]
  if (waiting > 0) parts.push(`${waiting} aguardando`)
  parts.push(`${ended} encerradas`)
  return `Splits: ${parts.join(', ')} (/splits abre o painel)`
}

export async function pollOnce($: Dollar): Promise<void> {
  const me = await $.session.id()
  const home = await homeDir($)
  const deliveredFile = `${home}/.claude/state/prompt-splitter-delivered.json`
  const doneGroups = async (): Promise<string[]> => [
    ...new Set([...(await read($, delivered)), ...parseDelivered(await readText($, deliveredFile))]),
  ]
  const records = parseRecords(await readText($, `${home}/.claude/state/prompt-splitter.jsonl`))
  const scope = await read($, scopeAtom)
  let current = await read($, view)
  const isParent = records.some(r => r.parent === me)
  const isChild = records.some(r => r.id === me.slice(0, 8))
  // Cheap path: with no splits, or none to show in 'mine' scope, the 'claude agents' process is skipped.
  const hasSplits = records.some(r => r.parent !== '')
  if (!hasSplits || (scope === 'mine' && !isParent && !isChild && current.mode !== 'detail')) {
    await $.ui.status(undefined)
    return
  }
  const now = await $.clock.now()
  const live = await readLive($)
  liveIds = new Map(live.flatMap(a => (a.sessionId ? [[a.id, a.sessionId] as [string, string]] : [])))
  // Only the groups whose parent is this session are delivered.
  const mine = buildRows(records, live, me, now)
  await fillAnswers($, mine)
  const recorded = new Map<string, string>()
  for (const r of records) if (r.parent_transcript) recorded.set(r.group, r.parent_transcript)

  const titled: SplitGroup[] = []
  const cwd = await $.session.cwd()
  for (const group of selectGroups(records, live, me, scope, now).filter(g => groupInCwd(g, cwd))) {
    await fillAnswers($, group.children)
    const path = await parentTranscriptPath($, home, group, recorded, now)
    titled.push({ ...group, parentTitle: await parentTitleOf($, group.parent, path, now) })
  }
  await update($, groupsAtom, () => titled)
  // A view on this session is not shown as a detail: the pane goes back to the list.
  if (isSelfView(current, titled, me)) {
    await update($, view, () => ({ mode: 'list' }))
    current = { mode: 'list' }
  }

  const selfGroup = titled.find(g => g.children.some(c => isSelfChild(c, me)))
  const selfChild = selfGroup?.children.find(c => isSelfChild(c, me))
  if ((mine.length > 0 || selfGroup !== undefined) && !opened) {
    opened = true
    const result = await $.ui.open({ id: PANE, title: 'Splits' })
    placed = result.isPlaced
  }
  // A refused pane is announced in the status line, so the user knows the /splits command opens it.
  let status: string | undefined
  if (!placed) {
    if (mine.length > 0) status = statusText(mine)
    else if (selfGroup && selfChild) status = childStatusText(selfChild, selfGroup.parentTitle)
  }
  // While prompts are routed to a node, the status line says where they go.
  const routed = routingTitle(current, titled, me)
  if (routed !== undefined) status = `Enviando para: ${routed}`
  await $.ui.status(status)

  if (current.mode === 'detail') {
    const group = titled.find(g => g.group === current.group)
    if (group && current.kind === 'child') {
      const child = group.children.find(c => c.id === current.id)
      if (child) {
        const path = childTranscriptPath(home, child)
        const lines = transcriptLines(await readText($, path))
        const subagents = await subagentCount($, path, now)
        await update($, transcript, () => ({ id: child.id, available: true, lines, subagents }))
      }
    } else if (group && current.kind === 'parent') {
      const path = await parentTranscriptPath($, home, group, recorded, now)
      const text = path === '' ? '' : await readText($, path)
      const lines = transcriptLines(text)
      const subagents = await subagentCount($, path, now)
      await update($, transcript, () => ({ id: current.id, available: text !== '', lines, subagents }))
    }
  }

  for (const group of readyGroups(mine, await doneGroups())) {
    if (inFlight.has(group)) continue
    inFlight.add(group)
    try {
      // Re-read right before delivering, so a group recorded meanwhile is never sent twice.
      const latest = await doneGroups()
      if (latest.includes(group)) continue
      const replies: { name: string; reply?: string }[] = []
      for (const kid of mine.filter(c => c.group === group)) {
        const reply = finalReply(await readTranscriptText($, kid))
        replies.push({ name: kid.name, reply })
      }
      // Recorded durably before submitting, so a restart or a lost $.state never resends it.
      // If the write fails, nothing is submitted and the group is retried on the next tick.
      try {
        await $.fs.write(deliveredFile, JSON.stringify([...latest, group]))
      } catch {
        continue
      }
      await update($, delivered, ids => (ids.includes(group) ? ids : [...ids, group]))
      await $.prompt.submit({ text: deliveryText(group, replies) })
    } finally {
      inFlight.delete(group)
    }
  }
}

async function safePoll($: Dollar): Promise<void> {
  try {
    await pollOnce($)
  } catch {
    // A failed poll is retried on the next tick.
  }
}

// Opens confirmed by the user's command: all splits, focused, placed at any terminal width.
async function showPanel($: Dollar): Promise<{ text: string }> {
  await update($, scopeAtom, () => 'all' as SplitScope)
  await update($, view, () => ({ mode: 'list' }))
  try {
    await pollOnce($)
  } catch {
    // The tree below shows whatever was loaded last.
  }
  const result = await $.ui.open(viewer ? { id: PANE, title: 'Splits', focus: true, rows: VIEWER_ROWS } : { id: PANE, title: 'Splits', focus: true })
  opened = true
  placed = result.isPlaced
  if (result.isPlaced) return { text: 'Painel Splits aberto.' }
  return { text: treeText(await read($, groupsAtom)) }
}

// Opens a detached Konsole window running the given claude command.
async function openWindow($: Dollar, cwd: string, args: string[]): Promise<void> {
  try {
    await $.process.run(['setsid', '-f', 'konsole', ...(cwd === '' ? [] : ['--workdir', cwd]), '-e', 'claude', ...args])
  } catch {
    // A failed launch leaves the pane as it is.
  }
}

export const register: Register = on => {
  let stopTimer: (() => void) | undefined

  on('session.start', async ($, e, next) => {
    const ran = await next(e)
    viewer = (await $.env.get('CLAUDE_SPLIT_VIEWER')) === '1'
    await $.command.register({ name: 'splits', description: 'Mostra o painel das sessoes divididas pelo prompt-splitter' })
    stopTimer?.()
    stopTimer = $.clock.every(POLL_MS, () => {
      void safePoll($)
    })
    // The viewer opens its pane by itself too; the `/splits` that claude-split.sh passes is the asked open.
    if (viewer) void showPanel($).catch(() => undefined)
    return ran
  })

  // After a dispatch the pane opens itself; the tool call is never altered or blocked.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const result = await next(e)
    try {
      const command = (e as { command?: unknown }).command
      if (typeof command === 'string' && command.includes('dispatch.py')) {
        await pollOnce($)
        const opening = await $.ui.open({ id: PANE, title: 'Splits' })
        opened = true
        placed = opening.isPlaced
      }
    } catch {
      // Opening the pane is best effort.
    }
    return result
  })

  on('command.run', { command: 'splits' }, ($) => showPanel($)).catch(($, e, next) =>
    next.called ? next(e) : { text: 'Painel Splits indisponivel.' },
  )

  on('command.run', { command: 'prompt-splitter:sessions' }, ($) => showPanel($)).catch(($, e, next) => next(e))

  // Closing the pane ends prompt routing: the view goes back to the list.
  on('ui.close', async ($, e, next) => {
    if (e.id === PANE) {
      await update($, detailOffset, () => ({ id: '', rows: 0, max: 0 }))
      await update($, view, () => ({ mode: 'list' }))
      // The viewer is the pane: a close by the person or a plugin only goes back to the list.
      if (viewer && e.origin.kind !== 'unload') return
    }
    return next(e)
  })

  // A plain prompt typed while a node is viewed goes to that node's session instead of this one.
  on('prompt.submit', async ($, e, next) => {
    // Outside the try: in viewer mode nothing may reach the model or be routed, even if the router breaks.
    const dropped = viewer ? viewerDrop(e) : undefined
    if (dropped !== undefined) return { drop: dropped }
    try {
      // Only the user's own composer submissions are routed; commands, meta prompts and other origins pass.
      if (e.command !== undefined || e.isMeta || e.origin?.kind !== 'composer') return next(e)
      const me = await $.session.id()
      const current = await read($, view)
      const groups = await read($, groupsAtom)
      const title = routingTitle(current, groups, me)
      if (title === undefined) return next(e)
      const target = routeTarget(current, groups, me, liveIds)
      if (target === undefined) {
        $.ui.toast('Sessao de destino ainda nao identificada: prompt mantido aqui')
        return next(e)
      }
      // The ticket lets the receiving child take the prompt as the person's own (see session.receive below).
      await addTicket($, target, { from: me, text: e.text, at: await $.clock.now() })
      const sent = await $.session.send({ to: { sessionId: target }, text: e.text })
      if (!sent.isDelivered) {
        $.ui.toast(`Nao enviado: ${sent.reason}`)
        return next(e)
      }
      return { drop: `Enviado para ${title}` }
    } catch {
      // A broken router must never break the user's prompt.
      return next(e)
    }
  })

  // In a child, a prompt the person typed in the parent's composer arrives as their own prompt instead of as
  // another session's message. Anything that fails the check in routedTicket keeps the default handling.
  on('session.receive', async ($, e, next) => {
    try {
      if (e.agentId !== undefined || e.origin.kind !== 'peer') return next(e)
      if ((await $.env.get('CLAUDE_SPLIT_CHILD')) !== '1') return next(e)
      const me = await $.session.id()
      const home = await homeDir($)
      const parent = registeredParent(parseRecords(await readText($, `${home}/.claude/state/prompt-splitter.jsonl`)), me)
      const path = routesPath(home, me)
      const tickets = parseTickets(await readText($, path))
      const i = routedTicket(e.origin, e.text, parent, tickets, await $.clock.now())
      if (i < 0) return next(e)
      const { text } = tickets[i]
      // Spend the ticket before resubmitting; if this write fails the delivery keeps the default handling.
      await $.fs.write(path, JSON.stringify(tickets.filter((_, j) => j !== i)))
      // Not awaited: the plugin's prompt runs once the session is idle, after this delivery is answered.
      void $.prompt.submit({ text, asUser: true }).catch(() => {
        $.ui.toast('Prompt da sessao principal nao pode ser enviado como seu')
      })
      return { consumed: 'prompt typed by the user in the parent session, resubmitted as their own' }
    } catch {
      return next(e)
    }
  })

  // In the detail view the transcript scrolls by its own offset; the header stays put. The list keeps the engine's scroll.
  on('ui.scroll', { requestId: PANE }, async ($, e, next) => {
    try {
      const current = await read($, view)
      const me = await $.session.id()
      const groups = await read($, groupsAtom)
      const viewed = isSelfView(current, groups, me) ? { mode: 'list' as const } : current
      if (viewed.mode !== 'detail' || layout.id !== viewed.id) return next(e)
      const state = await read($, detailOffset)
      const base = state.id === viewed.id ? state.rows : 0
      // e.by is negative toward the top: scrolling up adds rows from the bottom.
      const rows = Math.min(Math.max(base - e.by, 0), layout.max)
      await update($, detailOffset, () => ({ id: viewed.id, rows, max: layout.max }))
      $.ui.invalidate('ui.render')
      return {}
    } catch {
      return next(e)
    }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const me = await $.session.id()
    const current = await read($, view)
    const groups = await read($, groupsAtom)
    const scope = await read($, scopeAtom)
    const now = await $.clock.now()
    // A view on this session is shown as the list, never as a detail.
    const viewed = isSelfView(current, groups, me) ? { mode: 'list' as const } : current
    const group = viewed.mode === 'detail' ? groups.find(g => g.group === viewed.group) : undefined
    const child =
      viewed.mode === 'detail' && viewed.kind === 'child'
        ? group?.children.find(c => c.id === viewed.id)
        : undefined

    if (viewed.mode === 'detail' && group && (viewed.kind === 'parent' || child)) {
      const shown = await read($, transcript)
      const sameNode = shown.id === viewed.id
      const lines = sameNode ? shown.lines : []
      const subagents = sameNode ? (shown.subagents ?? 0) : 0
      const title = child ? child.label : group.parentTitle
      const titleColors = colorsOf(groups, me)
      const titleColor = child ? rowColor(child, titleColors) : titleColors.get(group.parent)
      const hint = child ? `claude attach ${child.id}` : `claude --resume ${group.parent}`
      const openNode = () => {
        if (child) void openWindow($, child.cwd, ['attach', child.id])
        else void openWindow($, group.parentCwd, ['--resume', group.parent])
      }
      const missing = !sameNode || lines.length === 0
      const missingText = !sameNode || shown.available ? 'Sem transcricao ainda.' : 'sem transcricao'
      // The pane's geometry is in the render's props; a missing one falls back to a usable size.
      const cols = e.props.bodyColumns || 40
      // The header stays fixed; the transcript gets the rest of the body and scrolls inside it.
      const headerRows =
        wrappedRows(title, cols) + wrappedRows(hint, cols) + 1 + (missing ? wrappedRows(missingText, cols) : 0)
      const avail = Math.max(1, (e.props.scroll?.bodyRows || 20) - headerRows)
      // Each block is one item of the window; its text lists the rows it takes (label, text, blank separator).
      const blocks = lines.map((line, i) => ({
        text: line.role === 'tool' ? `  · ${activityText(line)}` : `${line.role === 'voce' ? 'Voce' : 'Claude'}\n${line.text}\n`,
        node:
          line.role === 'tool' ? (
            <Text key={`line-${i}`} dimColor>{`  · ${activityText(line)}`}</Text>
          ) : (
            <Box key={`line-${i}`} flexDirection="column" marginBottom={1}>
              <Text bold color={line.role === 'voce' ? 'cyan' : 'magenta'}>
                {line.role === 'voce' ? 'Voce' : 'Claude'}
              </Text>
              <Text>{line.text}</Text>
            </Box>
          ),
      }))
      if (subagents > 0) {
        blocks.push({
          text: subagentsText(subagents),
          node: <Text key="subagents" dimColor>{subagentsText(subagents)}</Text>,
        })
      }
      const texts = blocks.map(b => b.text)
      const scroll = await read($, detailOffset)
      const requested = scroll.id === viewed.id ? scroll.rows : 0
      // A window with the "rolado" line at its bottom keeps one row for that line.
      const maxOffset = tailWindow(texts, Math.max(1, avail - 1), cols, 0).maxOffset
      let win = tailWindow(texts, avail, cols, requested)
      if (win.offset > 0) win = tailWindow(texts, Math.max(1, avail - 1), cols, win.offset)
      // Atoms are refused while drawing, so the layout the scroll hook clamps against is kept in the module.
      layout = { id: viewed.id, max: maxOffset }
      return (
        <Box flexDirection="column">
          <Box flexDirection="row">
            <Button
              key="back"
              autoFocus
              onPress={async () => {
                await update($, detailOffset, () => ({ id: '', rows: 0, max: 0 }))
                await update($, view, () => ({ mode: 'list' }))
              }}
            >
              {'< Voltar'}
            </Button>
            <Text>{'   '}</Text>
            <Button key="open" onPress={openNode}>
              {'Abrir em nova janela'}
            </Button>
          </Box>
          <Text bold color={titleColor}>{title}</Text>
          <Text dimColor>{hint}</Text>
          {missing && <Text dimColor>{missingText}</Text>}
          <Box flexDirection="column" height={avail} overflow="hidden">
            {blocks.slice(win.first, win.end).map(b => b.node)}
            {win.offset > 0 && <Text dimColor>{'  ... rolado (role para baixo para acompanhar)'}</Text>}
          </Box>
        </Box>
      )
    }

    const colors = colorsOf(groups, me)
    return (
      <Box flexDirection="column">
        <Button key="scope" onPress={() => update($, scopeAtom, s => (s === 'mine' ? 'all' : 'mine'))}>
          {scope === 'mine' ? 'Ver todas as sessoes' : 'So desta sessao'}
        </Button>
        {groups.length === 0 && (
          <Text dimColor>{scope === 'mine' ? 'Nenhum split nesta sessao.' : 'Nenhum split registrado.'}</Text>
        )}
        {groups.map(g => (
          <Box key={`group-${g.group}`} flexDirection="column">
            <Text dimColor>{groupLabel(g.startedMs, g.children.length)}</Text>
            {g.parent === me ? (
              <Text key={`parent-${g.group}`} dimColor>
                {`Esta sessao: ${g.parentTitle}`}
              </Text>
            ) : (
              <Button
                key={`parent-${g.group}`}
                onPress={() => update($, view, () => ({ mode: 'detail', kind: 'parent' as NodeKind, id: g.parent, group: g.group }))}
              >
                <Text color={colors.get(g.parent)}>{g.parentTitle}</Text>
              </Button>
            )}
            <Text>│</Text>
            {g.children.map((c, i) => {
              const connector = i === g.children.length - 1 ? '└──►' : '├──►'
              // Only an item that did not start yet (it depends on another process) is gray; the rest keep their color.
              const color = rowColor(c, colors)
              const text = `${connector} ${markOf(c)} ${c.itemLabel} ${c.label}  ${stateText(c, g.children)}  ${ageLabel(now - c.startedMs)}`
              if (c.isWaiting) {
                return (
                  <Text key={`child-${g.group}-${c.id}`} dimColor color={color}>
                    {text}
                  </Text>
                )
              }
              if (isSelfChild(c, me)) {
                return (
                  <Text key={`child-${g.group}-${c.id}`} dimColor>
                    {`${text}  (esta sessao)`}
                  </Text>
                )
              }
              return (
                <Button
                  key={`child-${g.group}-${c.id}`}
                  onPress={() => update($, view, () => ({ mode: 'detail', kind: 'child' as NodeKind, id: c.id, group: g.group }))}
                >
                  <Text color={color}>{text}</Text>
                </Button>
              )
            })}
          </Box>
        ))}
        {groups.length > 0 && <Text dimColor>{LEGEND}</Text>}
      </Box>
    )
  })
}
