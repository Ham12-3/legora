import { notFound } from 'next/navigation'

import { ReviewGrid } from '@/components/review/review-grid'
import { ApiError } from '@/lib/api'
import { workspaceApi } from '@/lib/server/api'
import type { ReviewDetail } from '@/lib/types'

type Props = { params: Promise<{ reviewId: string }> }

export default async function ReviewPage({ params }: Props) {
  const { reviewId } = await params
  let detail: ReviewDetail
  try {
    detail = await workspaceApi<ReviewDetail>(`/reviews/${reviewId}`)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound()
    throw error
  }
  return <ReviewGrid reviewId={reviewId} initial={detail} />
}
