// Small shared building blocks so every page uses the same buttons, fields and messages

const BUTTON_VARIANTS = {
  primary: 'bg-brand text-white hover:bg-brand-dark',
  secondary: 'border border-line bg-white text-ink hover:border-muted',
  danger: 'border border-bad/30 bg-white text-bad hover:bg-bad-soft',
  ghost: 'text-muted hover:bg-ink/5 hover:text-ink',
  // For the dark host stage
  stage: 'border border-white/25 text-white hover:bg-white/10',
};

const BUTTON_SIZES = {
  sm: 'min-h-9 px-3 text-sm',
  md: 'min-h-11 px-5 text-base',
  lg: 'min-h-14 px-7 text-lg',
};

export function Button({ variant = 'primary', size = 'md', className = '', ...props }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-control font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_VARIANTS[variant]} ${BUTTON_SIZES[size]} ${className}`}
      {...props}
    />
  );
}

export const inputClass =
  'w-full rounded-chip border border-line bg-white px-4 py-3 text-base text-ink placeholder:text-muted/70 transition-colors hover:border-muted focus-visible:border-brand';

export function Field({ label, hint, id, className = '', children }) {
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 block text-sm font-bold text-ink">
        {label}
        {hint && <span className="ml-1 font-normal text-muted">{hint}</span>}
      </label>
      {children}
    </div>
  );
}

export function Alert({ tone = 'error', children, action, onDismiss }) {
  const styles = tone === 'error' ? 'border-bad/25 bg-bad-soft text-bad' : 'border-ok/25 bg-ok-soft text-ok';
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`flex items-start justify-between gap-4 rounded-control border px-4 py-3 font-bold ${styles}`}>
      <span>{children}</span>
      {(action || onDismiss) && (
        <div className="flex shrink-0 items-center gap-3">
          {action}
          {onDismiss && (
            <button type="button" onClick={onDismiss} aria-label="Dismiss" className="rounded-chip px-1 text-xl leading-none opacity-60 hover:opacity-100">×</button>
          )}
        </div>
      )}
    </div>
  );
}

export function Panel({ as: Tag = 'section', className = '', ...props }) {
  return <Tag className={`rounded-panel border border-line bg-white ${className}`} {...props} />;
}

// Same PIN field on the guest form and the student dashboard
export const pinInputClass =
  'w-full rounded-chip border border-line bg-white px-4 py-3 text-center font-mono text-3xl font-extrabold tracking-[0.25em] text-ink uppercase placeholder:font-sans placeholder:text-lg placeholder:font-normal placeholder:tracking-normal placeholder:normal-case placeholder:text-muted/70 hover:border-muted focus-visible:border-brand';

export function Wordmark({ title }) {
  return (
    <span className="inline-flex items-center gap-3">
      {/* A single keycap: the app's answers are keys A-D, and this one is the question */}
      <span
        aria-hidden="true"
        className="inline-flex h-8 w-8 items-center justify-center rounded-[28%] border-b-[3px] border-black/35 bg-brand font-mono text-lg font-extrabold leading-none text-white"
      >
        ?
      </span>
      <span className="text-2xl font-bold tracking-tight">{title}</span>
    </span>
  );
}
