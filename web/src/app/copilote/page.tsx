import Link from "next/link";
import { redirect } from "next/navigation";

import { CopilotChat } from "@/components/CopilotChat";
import { CheckShieldIcon, DocumentIcon, LayersIcon, LockIcon, SparkIcon } from "@/components/icons";
import { PageBanner } from "@/components/PageBanner";
import { type Jurisdiction, api, currentAccount } from "@/lib/api";

/** Utiliser le Copilot (D3) : professionnel vérifié, agent d'autorité, validateur, responsable réglementaire, évaluateur. */
const COPILOT_ROLES = [
  "Professionnel vérifié",
  "Agent d'autorité",
  "Validateur",
  "Responsable réglementaire",
  "Évaluateur de pharmacovigilance",
];

const STEPS = [
  { icon: SparkIcon, title: "Le modèle comprend", text: "Il lit la question et choisit les outils du registre à interroger." },
  { icon: LayersIcon, title: "Le registre répond", text: "Les valeurs viennent d'enregistrements validés, jamais du modèle." },
  { icon: CheckShieldIcon, title: "La passerelle contrôle", text: "Chaque réponse est vérifiée avant d'être affichée, avec ses sources." },
];

export default async function CopilotPage() {
  const me = await currentAccount();
  if (!me) redirect("/connexion?next=/copilote");
  const allowed = me.roles.some((r) => COPILOT_ROLES.includes(r));
  const jurisdictions = await api<Jurisdiction[]>("/v1/jurisdictions");
  return (
    <>
      <PageBanner eyebrow="Assistant IA · modèle open source" title="Copilot">
        Questions sur le registre, en français ou en anglais, avec des réponses vérifiées et sourcées.
      </PageBanner>
      {allowed ? (
        <div className="copilot-layout">
          <CopilotChat jurisdictions={jurisdictions} defaultJurisdiction="PA" />
          <aside className="copilot-aside">
            <div className="section-title copilot-aside-title">
              <span className="section-kicker">Fonctionnement</span>
              <h2>Comment il répond</h2>
            </div>
            <ol className="copilot-steps">
              {STEPS.map(({ icon: Icon, title, text }) => (
                <li key={title} className="copilot-step">
                  <span className="copilot-step-icon" aria-hidden>
                    <Icon size={22} />
                  </span>
                  <div>
                    <h3>{title}</h3>
                    <p>{text}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="copilot-note">
              <DocumentIcon size={18} />
              <p>
                Pas de diagnostic ni de choix de traitement : le Copilot ne remplace pas le jugement clinique du
                vétérinaire.
              </p>
            </div>
          </aside>
        </div>
      ) : (
        <div className="copilot-locked">
          <span className="copilot-locked-icon" aria-hidden>
            <LockIcon size={30} />
          </span>
          <h2>Accès réservé</h2>
          <p>
            Le Copilot est réservé aux professionnels vérifiés et aux équipes réglementaires. Votre compte :{" "}
            {me.roles.join(", ")}.
          </p>
          <Link href="/connexion?next=/copilote" className="button pill">
            Changer de compte
          </Link>
        </div>
      )}
    </>
  );
}
