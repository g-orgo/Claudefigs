export type Pending = { id: string; rule: string; deadline: number }

declare module 'claude-code' {
  interface PluginState {
    'bom-senso-band': { pending: Pending | null; now: number }
  }
}
