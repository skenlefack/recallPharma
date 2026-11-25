import Link from "next/link";

import {
  ArrowRightIcon,
  BellIcon,
  BugIcon,
  CalendarIcon,
  ChatIcon,
  CheckShieldIcon,
  ClockIcon,
  CloseIcon,
  DocumentIcon,
  GlobeIcon,
  LayersIcon,
  MicroscopeIcon,
  PillIcon,
  SearchIcon,
  ThermometerIcon,
  UsersIcon,
  WormIcon,
} from "@/components/icons";
import { CountUp } from "@/components/CountUp";
import { AssessmentLine, NoticeBox, statusTone } from "@/components/regulatory";
import { Wave } from "@/components/Wave";
import { type Alert, ApiError, type Category, type Jurisdiction, type SearchResult, api, query } from "@/lib/api";
import { IMAGES } from "@/lib/images";

type Props = { searchParams: Promise<{ q?: string; category?: string; jurisdiction?: string; as_of?: string }> };

const CATEGORY_ICONS: Record<string, (p: { size?: number }) => React.ReactNode> = {
  antibiotiques: PillIcon,
  vermifuges: WormIcon,
  endectocides: BugIcon,
  antiprotozoaires: MicroscopeIcon,
  "anti-inflammatoires": ThermometerIcon,
};

const DISCOVER = [
  { href: "/?q=oxytétracycline", icon: CheckShieldIcon, image: IMAGES.carteStatut, title: "Statut des AMM", text: "Valide, suspendue, retirée, expirée" },
  { href: "/amm/amm-001#rcp", icon: DocumentIcon, image: IMAGES.carteRcp, title: "Texte des RCP", text: "Rubriques d'origine, page et source" },
  { href: "/amm/amm-002#rcp", icon: ClockIcon, image: IMAGES.carteDelais, title: "Délais d'attente", text: "Viande, lait, œufs : fin du délai calculée" },
  { href: "/alertes", icon: BellIcon, image: IMAGES.carteAlertes, title: "Alertes et rappels", text: "Suspensions, lots rappelés, falsifications" },
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
  const { q = "", category = "", jurisdiction = "", as_of = "" } = await searchParams;
  const [jurisdictions, categories] = await Promise.all([
    api<Jurisdiction[]>("/v1/jurisdictions"),
    api<Category[]>("/v1/categories").catch(() => [] as Category[]),
  ]);
  const active = categories.find((c) => c.code === category);
  const searching = q.trim().length >= 2 || active !== undefined;
  const alerts = searching ? [] : await api<Alert[]>("/v1/alerts").catch(() => [] as Alert[]);
  let result: SearchResult | null = null;
  let error: string | null = null;
  if (searching) {
    try {
      result = await api<SearchResult>(`/v1/search${query({ q: q.trim().length >= 2 ? q : "", category: active?.code, jurisdiction, as_of, limit: "100" })}`);
    } catch (e) {
      error = e instanceof ApiError ? e.message : "Recherche indisponible";
    }
  }
  const openAlerts = alerts.filter((a) => !a.closed_at);
  const counters = [
    { icon: GlobeIcon, value: jurisdictions.length, label: "juridictions couvertes" },
    { icon: BellIcon, value: openAlerts.length, label: "alertes en cours" },
    { icon: LayersIcon, value: 12, label: "rubriques de RCP indexées" },
    { icon: DocumentIcon, value: "A–D", label: "niveaux de preuve" },
  ];

  return (
    <>
      <section
        className={`home-hero full-bleed${searching ? " compact" : ""}`}
        style={{ backgroundImage: `url(${IMAGES.hero})` }}
      >
        <div className="home-hero-inner">
          <h1>{searching ? (active ? active.label : "Rechercher un médicament vétérinaire") : "Le bon médicament vétérinaire, avec sa preuve"}</h1>
          {!searching && (
            <p className="lead">
              Statut de l&apos;AMM, texte du RCP, délais d&apos;attente et alertes, pour un pays et une date.
            </p>
          )}
          <form className="hero-search" role="search" action="/">
            <label className="hero-field hero-field-main">
              <SearchIcon size={20} />
              <span className="sr-only">Recherche</span>
              {active && (
                <span className="hero-chip">
                  <input type="hidden" name="category" value={active.code} />
                  {active.label}
                  <Link href={`/${query({ q, jurisdiction, as_of })}`} aria-label={`Retirer la catégorie ${active.label}`}>
                    <CloseIcon size={12} />
                  </Link>
                </span>
              )}
              <input
                name="q"
                defaultValue={q}
                placeholder={active ? "Affiner…" : "Médicament, substance, n° d'AMM…"}
                aria-label="Recherche"
                minLength={2}
                required={!active}
              />
            </label>
            <label className="hero-field">
              <GlobeIcon size={18} />
              <span className="sr-only">Juridiction</span>
              <select name="jurisdiction" defaultValue={jurisdiction} aria-label="Juridiction">
                <option value="">Toutes les juridictions</option>
                {jurisdictions.map((j) => (
                  <option key={j.code} value={j.code}>
                    {j.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="hero-field hero-field-date">
              <CalendarIcon size={18} />
              <span className="sr-only">À la date du</span>
              <input type="date" name="as_of" defaultValue={as_of} aria-label="À la date du" />
            </label>
            <button type="submit" className="hero-submit" aria-label="Rechercher" title="Rechercher">
              <SearchIcon size={18} />
              <span>Rechercher</span>
            </button>
          </form>
          <nav className="hero-categories" aria-label="Catégories de médicaments">
            <span className="hero-categories-label">Parcourir</span>
            {categories.map((c) => {
              const Icon = CATEGORY_ICONS[c.code] ?? PillIcon;
              const current = c.code === category;
              return (
                <Link
                  key={c.code}
                  href={`/${query({ category: current ? "" : c.code, jurisdiction, as_of })}`}
                  className="hero-category"
                  title={c.description}
                  aria-current={current ? "true" : undefined}
                >
                  <span className="hero-category-icon" aria-hidden>
                    <Icon size={15} />
                  </span>
                  {c.label}
                  <span className="hero-category-count" aria-label={`${c.count} AMM`}>
                    {c.count}
                  </span>
                </Link>
              );
            })}
          </nav>
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
            <span className="muted small">
              {q && <>pour « {q} » </>}
              {active && <>dans {active.label.toLowerCase()} </>}· situation au {result.as_of}
            </span>
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
              <span className="section-kicker">Le registre</span>
              <h2>Ce que vous trouvez</h2>
              <p>Toutes les informations utiles à la prescription et à la délivrance</p>
            </div>
            <div className="offer-grid">
              {DISCOVER.map(({ icon: Icon, ...d }) => (
                <Link key={d.title} href={d.href} className="offer">
                  <span className="offer-media">
                    <span className="offer-img" style={{ backgroundImage: `url(${d.image})` }} />
                  </span>
                  <span className="offer-icon">
                    <Icon size={22} />
                  </span>
                  <span className="offer-body">
                    <span className="offer-title">{d.title}</span>
                    <span className="offer-text">{d.text}</span>
                    <span className="offer-more">
                      Découvrir <ArrowRightIcon size={14} />
                    </span>
                  </span>
                </Link>
              ))}
            </div>
          </section>

          <section className="why full-bleed" style={{ backgroundImage: `url(${IMAGES.fondPourquoi})` }}>
            <Wave flip />
            <div className="wrap">
              <div className="section-title on-dark">
                <span className="section-kicker">Nos engagements</span>
                <h2>Pourquoi RecallPharma</h2>
                <p>Une information vérifiée, datée et rattachée à sa source</p>
              </div>
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

          <section className="home-section counters-section">
            <div className="section-title">
              <span className="section-kicker">En chiffres</span>
              <h2>Le registre aujourd&apos;hui</h2>
              <p>Couverture actuelle du référentiel</p>
            </div>
            <div className="counters">
              {counters.map(({ icon: Icon, value, label }) => (
                <div key={label} className="counter">
                  <span className="counter-icon">
                    <Icon size={28} />
                  </span>
                  <strong>{typeof value === "number" ? <CountUp value={value} /> : value}</strong>
                  <span className="counter-label">{label}</span>
                </div>
              ))}
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
