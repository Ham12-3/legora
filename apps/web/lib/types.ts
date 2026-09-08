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
export type Chunk = Schemas['ChunkOut']

export type Review = Schemas['ReviewOut']
export type ReviewDetail = Schemas['ReviewDetail']
export type ReviewDocument = Schemas['ReviewDocumentOut']
export type ReviewColumn = Schemas['ColumnOut']
export type Cell = Schemas['CellOut']
export type Citation = Schemas['CitationOut']
export type CellStatus = Schemas['CellStatus']
export type OutputType = Schemas['OutputType']
export type ReviewRun = Schemas['RunOut']
export type RunRequest = Schemas['RunRequest']
export type ColumnCreate = Schemas['ColumnCreate']

export type Thread = Schemas['ThreadOut']
export type ThreadDetail = Schemas['ThreadDetail']
export type ThreadDocument = Schemas['ThreadDocumentOut']
export type Message = Schemas['MessageOut']
export type MessageCitation = Schemas['MessageCitation']

export type Playbook = Schemas['PlaybookOut']
export type PlaybookDetail = Schemas['PlaybookDetail']
export type PlaybookRule = Schemas['RuleOut']
export type PlaybookRun = Schemas['PlaybookRunOut']
export type PlaybookRunDetail = Schemas['PlaybookRunDetail']
export type Finding = Schemas['FindingOut']
