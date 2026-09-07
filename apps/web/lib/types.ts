/**
 * API types used by the web app, aliased from the OpenAPI-generated schema in
 * packages/shared. Regenerate with `pnpm gen:types` after changing a Pydantic
 * model; never hand-edit the generated file.
 */

import type { components } from '@legora/shared/api'

type Schemas = components['schemas']

export type Me = Schemas['MeOut']
export type Workspace = Schemas['WorkspaceOut']
export type WorkspaceDetail = Schemas['WorkspaceDetail']
export type Member = Schemas['MemberOut']
export type Role = Schemas['Role']
export type Matter = Schemas['MatterOut']
export type Document = Schemas['DocumentOut']
export type DocumentStatus = Schemas['DocumentStatus']
export type PresignResponse = Schemas['PresignResponse']
export type RegisterDocumentRequest = Schemas['RegisterDocumentRequest']
export type DownloadOut = Schemas['DownloadOut']
