/** Bord ondulé en bas (ou en haut) d'une section à fond image ; prend la couleur du fond de page. */
export function Wave({ flip = false, className }: { flip?: boolean; className?: string }) {
  return (
    <svg
      className={`wave${flip ? " wave-top" : ""}${className ? ` ${className}` : ""}`}
      viewBox="0 0 1440 120"
      preserveAspectRatio="none"
      aria-hidden
    >
      <path d="M0 64c120 28 260 46 420 30s300-62 470-58 300 52 430 52c50 0 90-6 120-14v46H0z" fill="var(--bg)" opacity=".45" />
      <path d="M0 84c150 22 300 30 470 10s310-50 470-42 290 44 400 44c40 0 72-4 100-10v34H0z" fill="var(--bg)" />
    </svg>
  );
}
