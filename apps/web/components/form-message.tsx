export function FormMessage({ error }: { error?: string | null }) {
  if (!error) return null
  return (
    <p role="alert" className="text-sm text-red-600 dark:text-red-400">
      {error}
    </p>
  )
}
