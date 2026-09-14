import type { ReactNode } from "react";

// Shared 24 px grid and rounded strokes keep every control visually consistent.
const shapes = {
  user: <><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></>,
  home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/><path d="M9 21v-8h6v8"/></>,
  image: <><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/></>,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/></>,
  cursor: <path d="m5 3 14 9-6 1-3 7L5 3Z"/>,
  hand: <><path d="M8 12V6a2 2 0 0 1 4 0v6-8a2 2 0 0 1 4 0v8-5a2 2 0 0 1 4 0v9c0 4-3 6-7 6-3 0-5-2-6-4l-4-6a2 2 0 0 1 3-2l2 2Z"/></>,
  expand: <path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>,
  link: <><path d="m10 13 4-4m-7 6-1 1a4 4 0 0 0 6 6l4-4a4 4 0 0 0 0-6m1-3 1-1a4 4 0 0 0-6-6L8 6a4 4 0 0 0 0 6" transform="translate(0 -1)"/></>,
  help: <><circle cx="12" cy="12" r="9"/><path d="M9 8a3 3 0 0 1 6 1c0 2-3 2-3 4m0 4h.01"/></>,
  menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
  more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
  message: <><path d="M21 11a8 8 0 0 1-8 8H7l-4 3V11a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z"/><path d="M7 9h10M7 13h6"/></>,
  team: <><circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m1-16a3 3 0 0 1 0 6m3 10v-3a6 6 0 0 0-3-5"/></>,
  plus: <path d="M12 5v14M5 12h14" />,
  arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  download: <><path d="M12 3v12m-5-5 5 5 5-5M5 16v4h14v-4" /></>,
  game: <><rect x="3" y="6" width="18" height="13" rx="4" /><path d="M8 10v5m-2.5-2.5h5" /><circle cx="16" cy="11" r=".8" /><circle cx="18" cy="14" r=".8" /></>,
  folder: <path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z" />,
  settings: <><path d="m10 3-.6 2.4-2 .9-2.2-.7-2 3.4 1.7 1.7v2.6L3.2 15l2 3.4 2.2-.7 2 .9L10 21h4l.6-2.4 2-.9 2.2.7 2-3.4-1.7-1.7v-2.6L20.8 9l-2-3.4-2.2.7-2-.9L14 3Z" /><circle cx="12" cy="12" r="3" /></>,
  sparkles: <><path d="m10 4 2.1 5.9L18 12l-5.9 2.1L10 20l-2.1-5.9L2 12l5.9-2.1L10 4ZM19 2v6m-3-3h6" /></>,
  rocket: <><path d="M9 15c0-7 5-11 12-12 0 7-4 12-11 12Zm1-7H6l-3 6h6m7 0v4l-6 3v-6M5 18l-2 3" /><circle cx="16" cy="8" r="1.5" /></>,
  target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" /></>,
  plan: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 3h6v3H9zM9 11h6m-6 4h4" /></>,
  code: <path d="m7 7-5 5 5 5m10-10 5 5-5 5M14 4l-4 16" />,
  check: <path d="m5 12 4 4L19 6" />,
  verified: <><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z" /><path d="m8 12 3 3 5-6" /></>,
  play: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="m10 8 6 4-6 4V8Z" /></>,
  diff: <><path d="M7 3v11a4 4 0 0 0 4 4h6M17 3v15" /><circle cx="7" cy="4" r="2" fill="var(--surface)" /><circle cx="17" cy="4" r="2" fill="var(--surface)" /><circle cx="17" cy="19" r="2" fill="var(--surface)" /></>,
  history: <><path d="M3 4v5h5M3 9a9 9 0 1 1 0 7" /><path d="M12 7v5l3 2" /></>,
  lock: <><rect x="5" y="10" width="14" height="11" rx="3" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" /></>,
} satisfies Record<string, ReactNode>;

export type StudioIconName = keyof typeof shapes;
export function StudioIcon({ name, size = 16 }: { name: StudioIconName; size?: number }) {
  return <svg className="studio-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{shapes[name]}</svg>;
}
