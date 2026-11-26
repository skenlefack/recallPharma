import Link from "next/link";

import {
  AlertTriangleIcon,
  ArrowRightIcon,
  ArrowUpIcon,
  BellIcon,
  CheckShieldIcon,
  DocumentIcon,
  HistoryIcon,
  UsersIcon,
} from "@/components/icons";
import { Logo } from "@/components/Logo";
import { IMAGES } from "@/lib/images";

const PROMISES = [
  { icon: DocumentIcon, title: "Preuve sourcée", text: "Chaque donnée renvoie au document officiel qui l'établit." },
  { icon: UsersIcon, title: "Double validation", text: "Deux validateurs indépendants avant toute publication." },
  { icon: BellIcon, title: "Alertes suivies", text: "Suspensions, retraits et rappels de lots datés." },
  { icon: HistoryIcon, title: "Journal d'audit", text: "Chaque modification tracée dans une chaîne vérifiable." },
];

const COLUMNS = [
  {
    title: "Consulter",
    links: [
      { href: "/", label: "Rechercher un médicament" },
      { href: "/alertes", label: "Alertes et rappels de lots" },
      { href: "/copilote", label: "Copilot vétérinaire" },
    ],
  },
  {
    title: "Catégories",
    links: [
      { href: "/?category=antibiotiques", label: "Antibiotiques" },
      { href: "/?category=vermifuges", label: "Vermifuges" },
      { href: "/?category=endectocides", label: "Endectocides" },
      { href: "/?category=anti-inflammatoires", label: "Anti-inflammatoires" },
    ],
  },
  {
    title: "Espace professionnel",
    links: [
      { href: "/connexion", label: "Connexion" },
      { href: "/validation", label: "Validation des données" },
      { href: "/validation/documents", label: "Documents sources" },
      { href: "/compte/securite", label: "Sécurité du compte" },
    ],
  },
];

/** Pied de page : engagements, navigation, avertissement d'usage et retour en haut. */
export function SiteFooter() {
  return (
    <footer className="site-footer" style={{ "--footer-img": `url(${IMAGES.fondFooter})` } as React.CSSProperties}>
      <div className="wrap">
        <ul className="footer-promises">
          {PROMISES.map(({ icon: Icon, title, text }) => (
            <li key={title} className="footer-promise">
              <span className="footer-promise-icon" aria-hidden>
                <Icon size={20} />
              </span>
              <span>
                <strong>{title}</strong>
                <span>{text}</span>
              </span>
            </li>
          ))}
        </ul>

        <div className="footer-grid">
          <div className="footer-about">
            <Link href="/" className="footer-brand" aria-label="RecallPharma, accueil">
              <Logo variant="sombre" height={54} />
            </Link>
            <p>
              Le référentiel du médicament vétérinaire : statut des AMM, texte des RCP, délais d&apos;attente et alertes,
              pour un pays et une date, avec leur preuve.
            </p>
            <span className="footer-badge">
              <CheckShieldIcon size={15} /> Données vérifiées par double validation
            </span>
          </div>
          {COLUMNS.map((col) => (
            <nav key={col.title} className="footer-col" aria-label={col.title}>
              <h4>{col.title}</h4>
              <ul>
                {col.links.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href}>
                      <ArrowRightIcon size={13} />
                      <span>{l.label}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <aside className="footer-warning">
          <span className="footer-warning-icon" aria-hidden>
            <AlertTriangleIcon size={18} />
          </span>
          <p>
            <strong>Outil d&apos;aide à la décision.</strong> RecallPharma ne remplace ni le jugement clinique du
            vétérinaire ni les décisions des autorités. Il n&apos;est pas informé systématiquement de toutes les
            suspensions et de tous les rappels : en cas de doute, vérifiez auprès de l&apos;autorité compétente.
          </p>
        </aside>
      </div>

      <div className="footer-bottom">
        <div className="wrap footer-bottom-inner">
          <span>
            © {new Date().getFullYear()} RecallPharma · Référentiel du médicament vétérinaire · intégré à RecallVET
          </span>
          <a href="#top" className="footer-top" aria-label="Retour en haut de la page">
            Haut de page <ArrowUpIcon size={15} />
          </a>
        </div>
      </div>
    </footer>
  );
}
