/** A small spinner to sit before a busy label. Decorative: the label next to it says what is happening. */
export function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg className={`mr-1.5 inline-block h-3.5 w-3.5 animate-spin align-[-2px] ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
