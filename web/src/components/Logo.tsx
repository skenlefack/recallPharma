/**
 * Logo RecallPharma (web/public/brand, extrait de public/images/logo.png sur fond transparent).
 * - « sombre » : texte blanc, pour l'en-tête et le pied de page ; sur petit écran, le mot seul sans la signature.
 * - « clair » : couleurs d'origine, avec la version blanche en mode sombre.
 */
const FULL = { width: 1070, height: 201 };
const WORDMARK = { width: 902, height: 131 };

export function Logo({ variant, height }: { variant: "sombre" | "clair"; height: number }) {
  const width = Math.round((FULL.width / FULL.height) * height);
  if (variant === "sombre") {
    return (
      <picture className="logo">
        <source
          media="(max-width: 720px)"
          srcSet="/brand/wordmark-blanc.png"
          width={Math.round((WORDMARK.width / WORDMARK.height) * 24)}
          height={24}
        />
        <img src="/brand/logo-blanc.png" alt="RecallPharma — Référentiel du médicament vétérinaire" width={width} height={height} />
      </picture>
    );
  }
  return (
    <picture className="logo">
      <source media="(prefers-color-scheme: dark)" srcSet="/brand/logo-blanc.png" />
      <img src="/brand/logo-couleur.png" alt="RecallPharma — Référentiel du médicament vétérinaire" width={width} height={height} />
    </picture>
  );
}
