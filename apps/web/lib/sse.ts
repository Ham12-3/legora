/**
 * Parse a fetch() body as Server-Sent Events. EventSource cannot POST, and the
 * assistant needs to send the question in the body, so the chat reads the
 * response stream and yields (event, data) pairs as they complete.
 */

export type SseEvent<T = unknown> = { event: string; data: T }

export function parseSseChunk(buffer: string): { events: SseEvent[]; rest: string } {
  const events: SseEvent[] = []
  let rest = buffer
  let index: number
  while ((index = rest.indexOf('\n\n')) !== -1) {
    const block = rest.slice(0, index)
    rest = rest.slice(index + 2)
    let event = 'message'
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      // comments (": keep-alive") and other fields are ignored
    }
    if (dataLines.length === 0) continue
    const raw = dataLines.join('\n')
    let data: unknown = raw
    try {
      data = JSON.parse(raw)
    } catch {
      // leave as text
    }
    events.push({ event, data })
  }
  return { events, rest }
}

export async function* readSse(response: Response): AsyncGenerator<SseEvent> {
  if (!response.body) return
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const { events, rest } = parseSseChunk(buffer)
      buffer = rest
      for (const e of events) yield e
    }
    const tail = parseSseChunk(buffer + '\n\n')
    for (const e of tail.events) yield e
  } finally {
    reader.releaseLock()
  }
}
