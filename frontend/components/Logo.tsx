export function LogoMark({ size = 22 }: { size?: number }) {
  // A forward line that loops back on itself: the reverse flow.
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect x="0.5" y="0.5" width="31" height="31" rx="3" fill="#F2F2F2" />
      <path d="M8 11.5h12.5a4.5 4.5 0 0 1 0 9H12" fill="none" stroke="#000" strokeWidth="2.6" strokeLinecap="square" />
      <path d="M14.5 16.8 11 20.5l3.5 3.7" fill="none" stroke="#000" strokeWidth="2.6" strokeLinecap="square" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark />
      <span className="text-[16px] font-semibold tracking-tight text-ink-900">ReverseFlow<span className="text-ink-500">.</span></span>
    </div>
  );
}
