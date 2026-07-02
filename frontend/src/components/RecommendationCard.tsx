import { Recommendation } from '../types';

interface RecommendationCardProps {
  item: Recommendation;
}

export default function RecommendationCard({ item }: RecommendationCardProps) {
  return (
    <article className="rounded-3xl border border-slate-700/80 bg-slate-950/80 p-5 shadow-glass">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-white">{item.name}</h3>
        <span className="rounded-full bg-cyan-500/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.18em] text-cyan-200">
          {item.test_type}
        </span>
      </div>
      <p className="text-sm leading-6 text-slate-400">A grounded SHL recommendation from the supplied catalog.</p>
      <a
        className="mt-4 inline-flex items-center gap-2 text-cyan-300 hover:text-cyan-100"
        href={item.url}
        target="_blank"
        rel="noreferrer"
      >
        View catalog item
      </a>
    </article>
  );
}
