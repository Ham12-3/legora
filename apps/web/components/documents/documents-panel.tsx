'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { IN_PROGRESS, StatusBadge } from '@/components/documents/status-badge'
import { Uploader } from '@/components/documents/uploader'
import { Button } from '@/components/ui/button'
import { clientApi } from '@/lib/client-api'
import { formatBytes, formatDate } from '@/lib/format'
import type { Document, DownloadOut } from '@/lib/types'

export function documentsKey(matterId: string) {
  return ['documents', matterId] as const
}

export function DocumentsPanel({
  matterId,
  initialDocuments,
}: {
  matterId: string
  initialDocuments: Document[]
}) {
  const queryClient = useQueryClient()

  const { data: documents = [] } = useQuery({
    queryKey: documentsKey(matterId),
    queryFn: () => clientApi<Document[]>(`/matters/${matterId}/documents`),
    initialData: initialDocuments,
    // Poll while anything is still moving through ingestion.
    refetchInterval: (query) =>
      query.state.data?.some((d) => IN_PROGRESS.has(d.status)) ? 5_000 : false,
  })

  const remove = useMutation({
    mutationFn: (documentId: string) =>
      clientApi<void>(`/documents/${documentId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: documentsKey(matterId) }),
  })

  async function open(documentId: string) {
    const { url } = await clientApi<DownloadOut>(`/documents/${documentId}/download`)
    window.open(url, '_blank', 'noopener')
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <section>
        <h2 className="text-lg font-semibold">
          Documents{' '}
          <span className="text-sm font-normal text-[var(--muted)]">({documents.length})</span>
        </h2>

        {documents.length === 0 ? (
          <p className="mt-6 text-sm text-[var(--muted)]">
            Nothing here yet. Drop PDFs or DOCX files on the right.
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto rounded-lg border border-[var(--border)]">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-[var(--muted)] dark:bg-slate-900">
                <tr>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Size</th>
                  <th className="px-4 py-2 font-medium">Uploaded</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {documents.map((d) => (
                  <tr key={d.id}>
                    <td className="max-w-xs px-4 py-2">
                      <button
                        type="button"
                        onClick={() => open(d.id)}
                        className="truncate text-left font-medium hover:underline"
                        title={d.filename}
                      >
                        {d.filename}
                      </button>
                      {d.error && (
                        <p className="mt-0.5 truncate text-xs text-red-600" title={d.error}>
                          {d.error}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <StatusBadge status={d.status} isOcr={d.is_ocr} />
                    </td>
                    <td className="px-4 py-2 tabular-nums text-[var(--muted)]">
                      {formatBytes(d.size_bytes)}
                    </td>
                    <td className="px-4 py-2 text-[var(--muted)]">{formatDate(d.created_at)}</td>
                    <td className="px-4 py-2 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={remove.isPending}
                        onClick={() => {
                          if (confirm(`Delete "${d.filename}"?`)) remove.mutate(d.id)
                        }}
                      >
                        Delete
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <aside>
        <Uploader
          matterId={matterId}
          onSettled={() => queryClient.invalidateQueries({ queryKey: documentsKey(matterId) })}
        />
      </aside>
    </div>
  )
}
