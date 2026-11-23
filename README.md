# RecallPharma

Référentiel du médicament vétérinaire intégré à RecallVET. Pour un produit, un pays et une date, il indique :
- si le produit est autorisé ;
- ce que dit son RCP ;
- quel délai d'attente s'applique ;
- s'il fait l'objet d'une alerte.

Chaque réponse est accompagnée de sa preuve. Le dossier de conception unifié fait référence : https://claude.ai/artifact/MJVeJRHVBkE5VxFat8uxkb

## État : incrément 1 (phase 1, lots 2 et 3)

| Brique | Contenu | Règles |
|---|---|---|
| Moteur de règles (`backend/src/recallpharma/domain`) | Statut calculé de l'AMM, échéance calculée, niveau de preuve A–D, mentions de revérification, bandeaux, délais d'attente, teneurs, vérification de lot ; fonctions pures, sans horloge ni base | RG-03 à RG-08, RG-11, RG-13 à RG-16, RG-19 à RG-22, RG-31 |
| Base (`backend/migrations`) | PostgreSQL 17 : schémas `reg` et `integration`, recherche sans accents et tolérante aux fautes (pg_trgm, unaccent), événements et audit en ajout seul, journal d'audit chaîné SHA-256 | RG-01, RG-08, RG-15, RG-33 |
| API (`backend/src/recallpharma/api`) | `/v1/search`, `/v1/authorisations/{id}` (fiche, `as_of` et `known_at`), `/v1/authorisations/{id}/withdrawal-end`, `/v1/alerts`, `/v1/batch-check`, erreurs RFC 9457 | RG-05, RG-06, RG-16, RG-18, RG-21, RG-22 |
| Jeu de démonstration | Annexe A10 : 60 AMM fictives et leurs résultats attendus, rejoués par les tests | — |

Les données sont **entièrement fictives** (annexe A10). Aucune AMM réelle n'est chargée tant que la convention avec le MINEPIA n'est pas signée.

## Démarrer

Prérequis : Docker et [uv](https://docs.astral.sh/uv/).

```sh
docker compose up -d                      # PostgreSQL 17 + pgvector sur le port 5434
cd backend
uv sync
uv run alembic upgrade head               # schéma
uv run python -m recallpharma.seed.load_db   # jeu fictif A10
RECALLPHARMA_REFERENCE_DATE=2027-09-07 uv run uvicorn recallpharma.api.app:app --reload
```

`RECALLPHARMA_REFERENCE_DATE` fige la date de consultation à celle du jeu A10. Sans elle, les statuts sont calculés à la date du jour.

La documentation interactive de l'API est servie sur http://localhost:8000/docs.

## Contrôles

```sh
uv run pytest            # 92 tests ; ceux de l'API créent une base recallpharma_test
uv run ruff check . && uv run ruff format --check .
uv run mypy              # typage strict
uv run lint-imports      # le domaine ne dépend ni de FastAPI, ni de SQLAlchemy, ni de Pydantic
```

## Choix à faire valider

- **Délai en jours (RG-21)** : « arrondi au début du jour suivant » est lu comme minuit du jour qui suit l'instant atteint, même si cet instant tombe déjà à minuit. C'est le choix le plus prudent. À confirmer par le pharmacien réglementaire.
- **Rappel de lot clos** : il continue de viser ses lots. La réponse reste « lot visé par un rappel publié » (RG-22).
- **Niveau A** : il exige aussi deux validations (RG-14). Une seule validation plafonne la donnée au niveau B.
- **Bitemporalité** : elle porte pour l'instant sur les événements réglementaires (`recorded_at`). Le versionnement champ par champ des fiches viendra avec le circuit de validation A → B → C.

## Suite prévue

1. Circuit de validation A → B → C avec ressaisie à l'aveugle, litiges et publication atomique (M02, RG-09 à RG-12, RG-32).
2. Interface web Next.js : recherche, fiche en cinq vues, alertes, back-office.
3. Comptes et rôles avec Keycloak.
4. Copilote : passerelle IA, modèle open source servi par vLLM, recherche hybride, contrôle après génération (RG-23 à RG-27).
