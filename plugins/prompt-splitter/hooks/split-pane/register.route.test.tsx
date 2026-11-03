import { expect, test } from 'claude-code/testing'

import { parseRecords, parseTickets, registeredParent, ROUTE_TTL_MS, routedTicket, unwrapEnvelope } from './register'

const NOW = 1_800_000_000_000
const ME = 'abcd1234-0000-0000-0000-000000000000'
const PARENT = 'parent00-0000-0000-0000-000000000000'
const RECORDS = parseRecords(
  [
    JSON.stringify({ id: 'abcd1234', name: 'a', cwd: '/w', parent: PARENT, group: 'g1', started: NOW - 60_000 }),
    JSON.stringify({ id: 'other999', name: 'b', cwd: '/w', parent: 'someone', group: 'g1', started: NOW - 60_000 }),
  ].join('\n'),
)
const FROM_SPLITTER = { kind: 'peer', plugin: 'prompt-splitter' }
const ticket = (from: string, text: string, at = NOW - 1_000) => ({ from, text, at })

test('registeredParent reads the parent of this session from its 8-char record id', () => {
  expect(registeredParent(RECORDS, ME)).toBe(PARENT)
  expect(registeredParent(RECORDS, 'zzzz9999-0000')).toBeUndefined()
})

test('a prompt-splitter message with a fresh ticket from the registered parent is taken as the user prompt', () => {
  const tickets = [ticket('someone', 'Congelou?'), ticket(PARENT, 'Congelou?')]
  expect(routedTicket(FROM_SPLITTER, 'Congelou?', PARENT, tickets, NOW)).toBe(1)
})

test('the engine envelope around the body does not prevent the match', () => {
  const wrapped =
    '<cross-session-message from="uds:/run/user/1000/cc-socks/1.sock" from-plugin="prompt-splitter">\nCongelou?\n</cross-session-message>'
  expect(unwrapEnvelope(wrapped)).toBe('Congelou?')
  expect(routedTicket(FROM_SPLITTER, wrapped, PARENT, [ticket(PARENT, 'Congelou?')], NOW)).toBe(0)
})

test('messages failing any part of the check keep the default cross-session handling', () => {
  const ok = [ticket(PARENT, 'Congelou?')]
  // Not composed by prompt-splitter, or written by the sending model itself.
  expect(routedTicket({ kind: 'peer', plugin: 'other-plugin' }, 'Congelou?', PARENT, ok, NOW)).toBe(-1)
  expect(routedTicket({ kind: 'peer' }, 'Congelou?', PARENT, ok, NOW)).toBe(-1)
  // Another origin kind, or a teammate mailbox entry.
  expect(routedTicket({ kind: 'bridge' }, 'Congelou?', PARENT, ok, NOW)).toBe(-1)
  expect(routedTicket({ ...FROM_SPLITTER, teammate: 'x', isVerified: false } as never, 'Congelou?', PARENT, ok, NOW)).toBe(-1)
  // A ticket from a session other than the registered parent, such as a sibling child.
  expect(routedTicket(FROM_SPLITTER, 'Congelou?', PARENT, [ticket('sibling', 'Congelou?')], NOW)).toBe(-1)
  // No registered parent for this session.
  expect(routedTicket(FROM_SPLITTER, 'Congelou?', undefined, ok, NOW)).toBe(-1)
  // A different text than the ticket's, an expired ticket, or no ticket at all.
  expect(routedTicket(FROM_SPLITTER, 'Outra coisa', PARENT, ok, NOW)).toBe(-1)
  expect(routedTicket(FROM_SPLITTER, 'Congelou?', PARENT, [ticket(PARENT, 'Congelou?', NOW - ROUTE_TTL_MS - 1)], NOW)).toBe(-1)
  expect(routedTicket(FROM_SPLITTER, 'Congelou?', PARENT, [], NOW)).toBe(-1)
})

test('parseTickets skips malformed content', () => {
  expect(parseTickets('not json')).toEqual([])
  expect(parseTickets(JSON.stringify([{ from: 'a', text: 'b', at: 1 }, { from: 'a' }]))).toEqual([{ from: 'a', text: 'b', at: 1 }])
})
