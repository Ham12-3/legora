/**
 * Types shared between the web app and the API.
 *
 * From Phase 1 these are generated from the Pydantic models rather than
 * hand-written. Until then this file holds only what both sides already agree
 * on.
 */

export type HealthStatus = {
  status: 'ok'
  environment: string
  version: string
}

export type ReadinessStatus = {
  status: 'ready' | 'degraded'
  postgres: boolean
  redis: boolean
}
