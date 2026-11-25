import Link from "next/link";

import {
  ArrowRightIcon,
  BellIcon,
  ChatIcon,
  CheckShieldIcon,
  ClockIcon,
  DocumentIcon,
  GlobeIcon,
  LayersIcon,
  SearchIcon,
  UsersIcon,
} from "@/components/icons";
import { AssessmentLine, NoticeBox, statusTone } from "@/components/regulatory";
import { Wave } from "@/components/Wave";
import { type Alert, ApiError, type Jurisdiction, type SearchResult, api, query } from "@/lib/api";
import { IMAGES } from "@/lib/images";

type Props = { searchParams: Promise<{ q?: string; jurisdiction?: string; as_of?: string }> };

const EXAMPLES = ["oxytétracycline", "ivermectine", "PA-V-2023-0002", "Gamma Vet"];

const DISCOVER = [
  { href: "/?q=oxytétracycline", image: IMAGES.carteStatut, title: "Statut des AMM", text: "Valide, suspendue, retirée, expirée" },
  { href: "/amm/amm-001#rcp", image: IMAGES.carteRcp, title: "Texte des RCP", text: "Rubriques d'origine, page et source" },
  { href: "/amm/amm-002#rcp", image: IMAGES.carteDelais, title: "Délais d'attente", text: "Viande, lait, œufs : fin du délai calculée" },
  { href: "/alertes", image: IMAGES.carteAlertes, title: "Alertes et rappels", text: "Suspensions, lots rappelés, falsifications" },
];

const WHY = [
  { icon: CheckShieldIcon, title: "Une preuve pour chaque information", text: "Niveau de preuve A à D, document source et date de vérification sur chaque fiche." },
  { icon: ClockIcon, title: "Délais d'attente calculés", text: "Date de fin du délai à partir du dernier traitement, par espèce et par denrée." },
  { icon: GlobeIcon, title: "Plusieurs juridictions", text: "Chaque AMM est lue avec son propre RCP, sans transposer d'un pays à l'autre." },
  { icon: UsersIcon, title: "Double validation", text: "Saisie, validation champ par champ puis ressaisie à l'aveugle avant publication." },
  { icon: BellIcon, title: "Alertes suivies", text: "Suspensions, retraits, rappels de lots et produits falsifiés signalés sur la fiche." },
  { icon: ChatIcon, title: "Copilot contrôlé", text: "Un modèle open source répond à partir du registre ; chaque valeur est vérifiée." },
];

export default async function SearchPage({ searchParams }: Props) {
  const { q = "", jurisdiction = "", as_of = "" } = await searchParams;
  const searching = q.trim().length >= 2;
  const [jurisdictions, alerts] = await Promise.all([
    api<Jurisdiction[]>("/v1/jurisdictions"),
    searching ? Promise.resolve([] as Alert[]) : api<Alert[]>("/v1/alerts").catch(() => [] as Alert[]),
  ]);
  let result: SearchResult | null = null;
  let error: string | null = null;
  if (searching) {
    try {
      result = await api<SearchResult>(`/v1/search${query({ q, jurisdiction, as_of })}`);
    } catch (e) {
      error = e instanceof ApiError ? e.message : "Recherche indisponible";
    }
  }
  const openAlerts = alerts.filter((a) => !a.closed_at);

  return (
    <>
      <section
        className={`home-hero full-bleed${searching ? " compact" : ""}`}
        style={{ backgroundImage: `url(${IMAGES.hero})` }}
      >
        <div className="home-hero-inner">
          <h1>{searching ? "Rechercher un médicament vétérinaire" : "Le bon médicament vétérinaire, avec sa preuve"}</h1>
          {!searching && (
            <p className="lead">
              Statut de l&apos;AMM, texte du RCP, délais d&apos;attente et alertes, pour un pays et une date.
            </p>
          )}
          <form className="hero-search" role="search" action="/">
            <label className="hero-search-main">
              <span className="sr-only">Recherche</span>
              <input
                name="q"
                defaultValue={q}
                placeholder="Nom, substance, numéro d'AMM ou titulaire"
                aria-label="Recherche"
                minLength={2}
                required
              />
            </label>
            <label>
              <span className="sr-only">Juridiction</span>
              <select name="jurisdiction" defaultValue={jurisdiction} aria-label="Juridiction">
                <option value="">Toutes les juridictions</option>
                {jurisdictions.map((j) => (
                  <option key={j.code} value={j.code}>
                    {j.name} ({j.code})
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="sr-only">À la date du</span>
              <input type="date" name="as_of" defaultValue={as_of} aria-label="À la date du" />
            </label>
            <button type="submit" aria-label="Rechercher" title="Rechercher">
              <SearchIcon size={20} />
            </button>
          </form>
          {!searching && (
            <div className="suggestions">
              Essayer :
              {EXAMPLES.map((e) => (
                <Link key={e} href={`/?q=${encodeURIComponent(e)}`}>
                  {e}
                </Link>
              ))}
            </div>
          )}
        </div>
        <Wave />
      </section>

      {error && <p className="error">{error}</p>}
      {result && (
        <section aria-live="polite">
          <div className="results-head">
            <h2>
              {result.hits.length} résultat{result.hits.length > 1 ? "s" : ""}
            </h2>
            <span className="muted small">pour « {q} » · situation au {result.as_of}</span>
          </div>
          {result.notice && <NoticeBox>{result.notice}</NoticeBox>}
          {result.hits.length === 0 && !result.notice && (
            <NoticeBox>Aucune AMM publiée ne correspond. L&apos;absence de résultat ne signifie pas une interdiction.</NoticeBox>
          )}
          <div className="stack" style={{ marginTop: 12 }}>
            {result.hits.map((h) => (
              <Link
                key={h.authorisation_id}
                href={`/amm/${h.authorisation_id}${query({ as_of })}`}
                className={`card hit status-${statusTone(h.assessment.status)}`}
              >
                <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                  <span className="title">
                    {h.product_name} — {h.designation}
                  </span>
                  <span className="mono small muted">{h.ma_number}</span>
                </div>
                <div className="meta">
                  <span className="chip">{h.holder}</span>
                  {h.substances.map((s) => (
                    <span key={s} className="chip">
                      {s}
                    </span>
                  ))}
                  <span className="chip">Juridiction {h.jurisdiction}</span>
                  {!h.applies_to_requested && <span className="chip tone-orange">AMM étrangère à la juridiction demandée</span>}
                </div>
                <div style={{ marginTop: 10 }}>
                  <AssessmentLine assessment={h.assessment} />
                </div>
                {h.assessment.banners.some((b) => b.level === "rouge") && (
                  <div className="small" style={{ marginTop: 8, color: "var(--red-fg)" }}>
                    ⛔ {h.assessment.banners.find((b) => b.level === "rouge")?.text}
                  </div>
                )}
              </Link>
            ))}
          </div>
        </section>
      )}

      {!searching && (
        <>
          <section className="home-section">
            <div className="section-title">
              <h2>Ce que vous trouvez</h2>
              <p>Toutes les informations utiles à la prescription et à la délivrance</p>
            </div>
            <div className="offer-grid">
              {DISCOVER.map((d) => (
                <Link key={d.title} href={d.href} className="offer">
                  <span className="offer-img" style={{ backgroundImage: `url(${d.image})` }} />
                  <span className="offer-title">{d.title}</span>
                  <span className="offer-text">{d.text}</span>
                </Link>
              ))}
            </div>
          </section>

          <section className="why full-bleed" style={{ backgroundImage: `url(${IMAGES.fondPourquoi})` }}>
            <Wave flip />
            <div className="wrap">
              <h2>Pourquoi RecallPharma</h2>
              <div className="why-grid">
                {WHY.map(({ icon: Icon, title, text }) => (
                  <div key={title} className="why-card">
                    <span className="why-icon">
                      <Icon size={24} />
                    </span>
                    <h3>{title}</h3>
                    <p>{text}</p>
                  </div>
                ))}
              </div>
            </div>
            <Wave />
          </section>

          <section className="counters">
            <div className="counter">
              <GlobeIcon size={42} />
              <strong>{jurisdictions.length}</strong>
              <span>juridictions couvertes</span>
            </div>
            <div className="counter">
              <BellIcon size={42} />
              <strong>{openAlerts.length}</strong>
              <span>alertes en cours</span>
            </div>
            <div className="counter">
              <LayersIcon size={42} />
              <strong>12</strong>
              <span>rubriques de RCP indexées</span>
            </div>
            <div className="counter">
              <DocumentIcon size={42} />
              <strong>A–D</strong>
              <span>niveaux de preuve</span>
            </div>
          </section>

          <section className="cta full-bleed" style={{ backgroundImage: `url(${IMAGES.fondCopilot})` }}>
            <Wave flip />
            <div className="wrap cta-inner">
              <h2>Une question sur un médicament ? Le Copilot répond à partir du registre.</h2>
              <Link href="/copilote" className="button pill">
                Poser une question <ArrowRightIcon size={16} />
              </Link>
            </div>
            <Wave />
          </section>
        </>
      )}
    </>
  );
}
