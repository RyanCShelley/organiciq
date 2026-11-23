"use client";

export function StyleNotesBanner({ styleNotes }: { styleNotes: string | null | undefined }) {
  const trimmed = styleNotes?.trim();
  if (!trimmed) return null;

  return (
    <div className="rounded-xl border border-[#ececec] bg-[#f8f8f8] px-4 py-3">
      <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
        Client tone &amp; style notes
      </div>
      <p className="mt-1 whitespace-pre-line text-[13px] text-[#171a22]">{trimmed}</p>
    </div>
  );
}
