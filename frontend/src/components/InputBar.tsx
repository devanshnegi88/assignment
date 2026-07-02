interface InputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
}

export default function InputBar({ value, onChange, onSubmit, disabled = false }: InputBarProps) {
  return (
    <div className="flex flex-col gap-3">
      <label htmlFor="chat-input" className="text-sm text-slate-400">
        Ask the agent about SHL assessments.
      </label>
      <div className="flex gap-3">
        <textarea
          id="chat-input"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          rows={3}
          className="min-h-[96px] flex-1 resize-none rounded-3xl border border-slate-700/80 bg-slate-900/80 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400/80 focus:ring-2 focus:ring-cyan-400/20"
          placeholder="e.g. Hiring a mid-professional SQL developer"
          disabled={disabled}
        />
        <button
          type="button"
          onClick={onSubmit}
          disabled={disabled}
          className="inline-flex min-h-[56px] items-center justify-center rounded-3xl bg-cyan-500 px-6 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Send
        </button>
      </div>
    </div>
  );
}
