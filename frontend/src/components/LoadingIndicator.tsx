export default function LoadingIndicator() {
  return (
    <div className="mt-4 flex items-center gap-3 rounded-3xl border border-slate-700/70 bg-slate-900/80 px-4 py-4 text-sm text-slate-300">
      <div className="h-3 w-3 animate-pulse rounded-full bg-cyan-300" />
      <span>Loading recommendations...</span>
    </div>
  );
}
