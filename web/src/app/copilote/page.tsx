import { redirect } from "next/navigation";

import { CopilotChat } from "@/components/CopilotChat";
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

export default async function CopilotPage() {
  const me = await currentAccount();
  if (!me) redirect("/connexion?next=/copilote");
  const allowed = me.roles.some((r) => COPILOT_ROLES.includes(r));
  const jurisdictions = await api<Jurisdiction[]>("/v1/jurisdictions");
  return (
    <>
      <PageBanner eyebrow="Assistant IA · modèle open source" title="Copilot">
        Questions sur le registre, en français ou en anglais. Chaque valeur affichée vient d&apos;un enregistrement validé :
        le modèle choisit les outils et rédige les phrases de liaison, la passerelle insère les valeurs et contrôle la
        réponse avant de l&apos;afficher. Pas de diagnostic ni de choix de traitement.
      </PageBanner>
      {allowed ? (
        <CopilotChat jurisdictions={jurisdictions} defaultJurisdiction="PA" />
      ) : (
        <div className="banner tone-orange" role="status">
          <div>
            Le Copilot est réservé aux professionnels vérifiés et aux équipes réglementaires. Votre compte :{" "}
            {me.roles.join(", ")}.
          </div>
        </div>
      )}
    </>
  );
}
