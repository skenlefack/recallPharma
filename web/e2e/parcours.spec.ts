import { createHmac } from "node:crypto";

import { type Page, expect, test } from "@playwright/test";

/** Connexion réelle par Keycloak (royaume de développement). Effacer les cookies ferme aussi la session Keycloak. */
async function login(page: Page, account: string) {
  await page.context().clearCookies();
  await page.goto("/connexion?next=/validation");
  await page.getByLabel("Adresse e-mail").fill(`demo${account.slice(-2)}@recallpharma.example`);
  await page.getByLabel("Mot de passe", { exact: true }).fill("demo-recallpharma");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/localhost:3100\/validation/);
}

const card = (page: Page, title: string) => page.locator(".card", { has: page.getByRole("heading", { name: title, exact: true }) });

test("consultation : recherche tolérante, bandeau rouge, délai d'attente, lot", async ({ page }) => {
  await page.goto("/?q=oxytetracyline");
  await expect(page.getByRole("heading", { name: /résultat/ })).toBeVisible();
  await page.goto("/amm/amm-002");
  await expect(page.getByRole("alert").first()).toContainText("AMM suspendue dans cette juridiction");
  await expect(page.getByText("AMM suspendue", { exact: true })).toBeVisible();

  const calc = card(page, "Calculer la fin du délai d'attente");
  await calc.getByLabel("Espèce").selectOption("bovins");
  await calc.getByLabel("Denrée").selectOption("viande et abats");
  await calc.getByLabel("Voie").selectOption("IM");
  await calc.getByLabel("Dernière administration").fill("2027-09-07T14:30");
  await calc.getByRole("button", { name: "Calculer" }).click();
  await expect(calc).toContainText("Première collecte ou premier abattage possible à partir du 2027-09-22 00:00");

  await page.goto("/amm/amm-001");
  const lot = card(page, "Vérifier un numéro de lot");
  await lot.getByLabel("Numéro de lot").fill("L27-0412");
  await lot.getByRole("button", { name: "Vérifier" }).click();
  await expect(lot).toContainText("lot visé par un rappel publié");
  await expect(lot).toContainText("Ne constitue pas une authentification.");
});

test("connexion : un compte sans rôle de validation ne peut pas préparer, la déconnexion ferme la session", async ({ page }) => {
  await login(page, "cpt-03");
  await expect(page.locator("header .who")).toContainText("Professionnel vérifié (cpt-03)");
  await expect(page.getByRole("status")).toContainText("Ce compte ne peut ni préparer ni valider");
  await page.goto("/connexion");
  await page.getByRole("button", { name: "Se déconnecter" }).first().click();
  await expect(page.locator("header .who")).toContainText("Se connecter");
  await page.goto("/validation");
  await expect(page).toHaveURL(/\/connexion/);
});

test("circuit A → B → C : une nouvelle AMM est publiée après double validation", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now().toString().slice(-6);
  const maNumber = `PA-V-2027-E${stamp}`;

  // A dépose le document source et prépare la fiche
  await login(page, "cpt-06");
  await page.goto("/validation/documents");
  await page.getByLabel("Fichier (PDF, image)").setInputFiles({
    name: `decision-${stamp}.pdf`,
    mimeType: "application/pdf",
    buffer: Buffer.from(`%PDF-1.7 décision fictive ${stamp}`),
  });
  await page.getByLabel("Titre").fill(`Décision d'AMM ${stamp} (SPÉCIMEN)`);
  await page.getByLabel("Date du document").fill("2027-08-20");
  await page.getByRole("button", { name: "Déposer" }).click();
  await expect(page.getByText(/Document n° \d+ enregistré/)).toBeVisible();

  await page.goto("/validation/nouvelle");
  const amm = card(page, "AMM");
  await amm.getByLabel("Numéro d'AMM").fill(maNumber);
  await amm.getByLabel("Titulaire").fill("Laboratoires Alpha (fictif)");
  await amm.getByLabel("Date d'octroi").fill("2027-08-15");
  await amm.getByRole("button", { name: "Ajouter un événement" }).click();
  const product = card(page, "Produit");
  await product.getByLabel("Dénomination").fill(`Produit-E${stamp}`);
  await product.getByLabel("Désignation").fill("florfénicol 300 mg/mL, solution injectable");
  await product.getByLabel("Forme pharmaceutique").fill("solution injectable");
  await product.getByLabel("Voies (séparées par des virgules)").fill("IM");
  await product.getByLabel("Espèces cibles").fill("bovins");
  await product.getByRole("button", { name: "Ajouter une substance" }).click();
  await product.getByLabel("Substance").selectOption({ label: "florfénicol" });
  await product.getByLabel("Teneur telle qu'écrite").fill("300 mg/mL");
  await product.getByLabel("Valeur").fill("300");
  await product.getByLabel("Unité").fill("mg");
  await product.getByLabel("Base").fill("par mL");
  const rcp = card(page, "RCP");
  await rcp.getByLabel("Posologie").fill("20 mg/kg en IM, deux injections à 48 h d'intervalle");
  await rcp.getByRole("button", { name: "Ajouter un délai" }).click();
  await rcp.getByLabel("Espèce", { exact: true }).fill("bovins");
  await rcp.getByLabel("Denrée", { exact: true }).fill("viande et abats");
  await rcp.getByLabel("Voie", { exact: true }).fill("IM");
  await rcp.getByLabel("Valeur", { exact: true }).fill("30");
  await page.getByRole("button", { name: "Appliquer à tous les champs" }).click();
  await page.getByRole("button", { name: "Créer la proposition" }).click();
  await expect(page.getByRole("heading", { name: /Proposition #\d+/ })).toBeVisible();
  const url = page.url();
  await page.getByRole("button", { name: "Soumettre" }).click();
  await expect(page.locator("h1 .badge")).toHaveText("en première validation");

  // B affiche chaque source, confirme, valide
  await login(page, "cpt-13");
  await page.goto(url);
  const sources = page.getByRole("button", { name: "Afficher la source" });
  await expect(page.getByRole("button", { name: "Valider" })).toBeDisabled();
  const total = await sources.count();
  expect(total).toBe(14);
  for (let left = total; left > 0; left--) {
    await sources.first().click();
    await expect(sources).toHaveCount(left - 1);
  }
  for (const box of await page.getByRole("checkbox").all()) await box.check();
  await page.getByRole("button", { name: "Valider" }).click();
  await expect(page.locator("h1 .badge")).toHaveText("en seconde validation");

  // C ressaisit à l'aveugle (écritures différentes mais concordantes)
  await login(page, "cpt-07");
  await page.goto(url);
  await expect(page.getByText("masqué pour la ressaisie").first()).toBeVisible();
  const blind = card(page, "Seconde validation à l'aveugle (C)");
  await blind.getByLabel("Numéro d'AMM").fill(maNumber.toLowerCase().replaceAll("-", " "));
  await blind.getByLabel("Teneur de florfénicol (telle qu'écrite)").fill("300 mg/ml");
  await blind.getByLabel("Posologie").fill("20 mg/kg en IM, deux injections à 48 h d'intervalle");
  await blind.getByRole("button", { name: "Ajouter un délai" }).click();
  await blind.getByLabel("Espèce", { exact: true }).fill("bovins");
  await blind.getByLabel("Denrée", { exact: true }).fill("viande et abats");
  await blind.getByLabel("Voie", { exact: true }).fill("IM");
  await blind.getByLabel("Valeur", { exact: true }).fill("30");
  await blind.getByRole("button", { name: "Enregistrer la ressaisie" }).click();
  await expect(page.locator("h1 .badge")).toHaveText("publiée");

  // La fiche est désormais publique
  await page.goto(`/?q=${maNumber}`);
  await expect(page.getByText(`Produit-E${stamp}`)).toBeVisible();
  await page.getByText(`Produit-E${stamp}`).click();
  await expect(page.getByText("Preuve A · Confirmé")).toBeVisible();
});

test("copilot : tableau du registre, réponse contrôlée, affinage, abstention, signalement", async ({ page }) => {
  // Prérequis : passerelle sur :8001 ; le faux modèle (backend/tests/fake_llm.py) suffit pour ce parcours.
  await login(page, "cpt-03");
  await page.goto("/copilote");
  const ask = async (q: string) => {
    await page.getByLabel(/Votre question/).fill(q);
    await page.getByRole("button", { name: "Envoyer" }).click();
    await expect(page.getByRole("button", { name: "Envoyer" })).toBeVisible({ timeout: 60_000 });
  };

  await ask("Quels produits à base d'ivermectine sont autorisés pour les bovins ?");
  const turn = page.locator(".copilot-turn").nth(0);
  await expect(turn.locator("tbody tr")).toHaveCount(2);
  await expect(turn).toContainText("2 enregistrements du registre");
  await expect(turn).toContainText("Le registre compte 2 produits pour cette recherche.");
  await expect(turn).toContainText("Juridiction : Pays A · vérification la plus ancienne : 2027-07-13 · niveau de preuve le plus faible : A");
  await expect(turn).toContainText("Ne remplace pas le jugement clinique du vétérinaire.");

  await ask("Lesquels sont injectables ?");
  await expect(page.locator(".copilot-turn").nth(1).locator("tbody tr")).toHaveCount(2);

  await ask("Quel traitement choisir pour une vache qui tousse ?");
  await expect(page.locator(".copilot-turn").nth(2)).toContainText("ne dispose pas de données vérifiées");

  await turn.getByRole("button", { name: "Signaler une erreur" }).click();
  await expect(turn).toContainText(/Signalement reçu \(ticket QUAL-\d+\)/);
});

test("administration : tableau de bord pour l'administrateur, accès refusé au visiteur", async ({ page }) => {
  await login(page, "cpt-09");
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Tableau de bord" })).toBeVisible();
  await expect(page.getByText("AMM publiées", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Journal d'audit" }).click();
  await expect(page.getByText("Chaîne intacte")).toBeVisible();

  await login(page, "cpt-01");
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Administration réservée" })).toBeVisible();
});

/** Code TOTP (RFC 6238, SHA-1, 6 chiffres, 30 s) calculé comme une application d'authentification. */
function totp(secret: string, at = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of secret) bits += alphabet.indexOf(c).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)));
  const digest = createHmac("sha1", key).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

test("double authentification : activation, connexion avec code, refus d'un code faux, désactivation", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page, "cpt-04");
  await page.goto("/compte/securite");
  await page.getByRole("button", { name: "Activer la double authentification" }).click();
  const secret = (await page.locator(".mfa-secret").innerText()).trim();
  await page.getByLabel("Code à 6 chiffres").fill(totp(secret));
  await page.getByRole("button", { name: "Confirmer et activer" }).click();
  await expect(page.getByText("Double authentification active", { exact: true })).toBeVisible();

  // Nouvelle connexion : le mot de passe ne suffit plus.
  await page.context().clearCookies();
  await page.goto("/connexion?next=/compte/securite");
  await page.getByLabel("Adresse e-mail").fill("demo04@recallpharma.example");
  await page.getByLabel("Mot de passe", { exact: true }).fill("demo-recallpharma");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("heading", { name: "Code de vérification" })).toBeVisible();
  await page.getByLabel("Code à 6 chiffres").fill("000000");
  await page.getByRole("button", { name: "Vérifier" }).click();
  await expect(page.locator(".auth-error")).toContainText("Code incorrect");
  await page.getByLabel("Code à 6 chiffres").fill(totp(secret, Date.now() + 30_000));
  await page.getByRole("button", { name: "Vérifier" }).click();
  await expect(page).toHaveURL(/\/compte\/securite/);

  // Désactivation : un code déjà utilisé est refusé (anti-rejeu), on attend donc le pas de 30 s suivant.
  await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500);
  await page.getByLabel("Code à 6 chiffres").fill(totp(secret, Date.now() + 30_000));
  await page.getByRole("button", { name: "Désactiver" }).click();
  await expect(page.getByText("Double authentification désactivée.")).toBeVisible();
});
