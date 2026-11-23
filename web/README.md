# RecallPharma — interface web

Next.js (App Router, TypeScript), rendu côté serveur. Le serveur Next.js sert aussi de BFF (ADR-04) :
- le navigateur n'appelle jamais l'API FastAPI directement ;
- les pages serveur interrogent l'API avec l'identité de la session ;
- les actions du navigateur passent par `/api/bff/*`, qui refuse les requêtes venant d'une autre origine ;
- l'identité est gardée dans un cookie `HttpOnly` et `SameSite=Strict`.

| Page | Rôle |
|---|---|
| `/` | Recherche (nom, substance, n° d'AMM, titulaire), filtre par juridiction et par date |
| `/amm/[id]` | Fiche en cinq vues : identité, réglementation, RCP et délais (avec calculateur), preuves, alertes et vérification de lot |
| `/alertes` | Alertes publiées, filtrables par juridiction |
| `/connexion` | Choix d'un compte fictif du jeu A10, en attendant Keycloak |
| `/validation` | Propositions classées par état, avec l'étape à faire selon le compte connecté |
| `/validation/documents` | Dépôt des documents sources (empreinte, versions) |
| `/validation/nouvelle`, `/validation/[id]` | Saisie (A), première validation avec affichage des sources (B), ressaisie à l'aveugle (C), arbitrage |

## Démarrer

```sh
pnpm install
RECALLPHARMA_API_URL=http://127.0.0.1:8000 pnpm dev   # API démarrée au préalable (voir ../README.md)
```

Après une modification de l'API, régénérer les types du contrat :

```sh
(cd ../backend && uv run python -m recallpharma.api.export_openapi ../web/openapi.json)
pnpm exec openapi-typescript openapi.json -o src/lib/api-types.ts
```

## Contrôles

```sh
pnpm exec tsc --noEmit && pnpm lint && pnpm build
pnpm exec playwright install chromium   # une fois
pnpm exec playwright test               # parcours de bout en bout ; API sur :8000 avec RECALLPHARMA_REFERENCE_DATE=2027-09-07
```
