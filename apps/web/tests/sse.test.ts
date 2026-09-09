import { describe, expect, it } from 'vitest'

import { parseSseChunk, readSse } from '@/lib/sse'

describe('parseSseChunk', () => {
  it('parses complete events and keeps the incomplete tail', () => {
    const { events, rest } = parseSseChunk(
      'event: status\ndata: {"stage":"retrieving"}\n\nevent: delta\ndata: {"text":"Hel',
    )
    expect(events).toEqual([{ event: 'status', data: { stage: 'retrieving' } }])
    expect(rest).toBe('event: delta\ndata: {"text":"Hel')
  })

  it('ignores keep-alive comments and defaults the event name', () => {
    const { events } = parseSseChunk(': keep-alive\n\ndata: {"a":1}\n\n')
    expect(events).toEqual([{ event: 'message', data: { a: 1 } }])
  })
})

describe('readSse', () => {
  it('yields events across arbitrary chunk boundaries', async () => {
    const body =
      'event: delta\ndata: {"text":"one "}\n\nevent: delta\ndata: {"text":"two"}\n\nevent: message\ndata: {"role":"assistant"}\n\n'
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (let i = 0; i < body.length; i += 7)
          controller.enqueue(encoder.encode(body.slice(i, i + 7)))
        controller.close()
      },
    })
    const events = []
    for await (const e of readSse(new Response(stream))) events.push(e)
    expect(events.map((e) => e.event)).toEqual(['delta', 'delta', 'message'])
    expect(events[1]?.data).toEqual({ text: 'two' })
  })
})
