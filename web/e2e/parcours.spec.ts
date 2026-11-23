import { type Page, expect, test } from "@playwright/test";

async function login(page: Page, account: string) {
  await page.goto("/connexion");
  await page.locator(`input[name=account][value=${account}]`).check();
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/\/validation/);
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
