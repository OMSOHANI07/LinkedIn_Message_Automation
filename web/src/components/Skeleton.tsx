export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-paper-sunken ${className}`} />
}

export function NoteCardSkeleton() {
  return (
    <div className="rounded-lg border border-hairline bg-paper-raised p-4">
      <div className="flex items-center gap-2">
        <Skeleton className="h-5 w-16" />
        <Skeleton className="h-5 w-24" />
      </div>
      <Skeleton className="mt-3 h-4 w-full" />
      <Skeleton className="mt-2 h-4 w-4/5" />
      <Skeleton className="mt-3 h-3 w-2/3" />
    </div>
  )
}
