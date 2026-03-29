# Webapp Replication Manual

> Ez a dokumentum leírja, mit kell módosítani, ha az FM/PM/AM platformot egy másik iparágra replikáljuk.
> A keretrendszer (framework) általános részei újrafelhasználhatók; csak a webapp-specifikus részeket kell cserélni.

## Architektúra: Framework vs Webapp

```
OnjaroWeb/
├── research/                  # FRAMEWORK - általános, ne módosítsd
│   ├── pipeline/              # fetch → extract → validate → normalize → dedupe → persist
│   ├── config_loader.py       # YAML config betöltő
│   ├── models.py              # ExtractionCandidate, stb.
│   └── supabase_client.py     # Supabase kapcsolat
│
├── orchestrator/              # FRAMEWORK - általános
│   ├── main.py                # Fő orchestrator
│   ├── research_run_manager.py
│   └── event_bus.py
│
├── db/                        # FRAMEWORK - általános
│   └── research_repository.py
│
├── webapp/                    # WEBAPP-SPECIFIKUS - ezt kell replikálni
│   ├── research_config/       # ← Iparág-specifikus kutatási konfiguráció
│   │   ├── items.yaml         # Kutatási témák, ütemezés
│   │   ├── policies.yaml      # Deduplikáció, jóváhagyás szabályok
│   │   ├── prompts/
│   │   │   ├── search_prompts.yaml    # Keresési promptok
│   │   │   └── extract_prompts.yaml   # Kinyerési promptok (entitástípusonként)
│   │   ├── schemas/           # Pydantic sémák a kinyert entitásokhoz
│   │   │   ├── company.py
│   │   │   ├── building.py
│   │   │   ├── person.py
│   │   │   └── news_mention.py
│   │   └── mappings/
│   │       └── persistence.yaml  # Mező-leképezések: extraction → Supabase oszlop
│   │
│   ├── supabase/
│   │   └── schema.sql         # ← Adatbázis séma (iparág-specifikus táblák)
│   │
│   ├── src/
│   │   ├── lib/
│   │   │   ├── types.ts       # ← TypeScript típusok (séma tükör)
│   │   │   ├── utils.ts       # ← Címkék, fordítások, formázók
│   │   │   ├── supabase.ts    # Supabase kliens (általános)
│   │   │   └── db/            # ← Supabase lekérdezések (tábla-specifikus)
│   │   │       ├── companies.ts
│   │   │       ├── buildings.ts
│   │   │       ├── people.ts
│   │   │       ├── changes.ts
│   │   │       └── stats.ts
│   │   │
│   │   ├── app/
│   │   │   ├── page.tsx           # ← Főoldal (iparág-specifikus szövegek)
│   │   │   ├── cegek/             # ← Entitás oldalak (FM/PM/AM specifikus)
│   │   │   ├── ingatlanok/
│   │   │   ├── emberek/
│   │   │   ├── valtozasok/
│   │   │   ├── modszertan/
│   │   │   ├── admin/             # Admin felület
│   │   │   │   ├── login/         # ← Belépés (általános)
│   │   │   │   ├── entities/      # ← CRUD (általános, config-vezérelt)
│   │   │   │   ├── prompts/       # ← Prompt szerkesztő (általános)
│   │   │   │   └── tips/          # ← Research tippek (általános)
│   │   │   └── api/
│   │   │       └── admin/         # Admin API route-ok
│   │   │
│   │   └── components/
│   │       ├── admin/             # ← Admin komponensek (általános)
│   │       └── [public components]  # ← Publikus kártyák, stb. (specifikus)
│   │
│   └── .env.local             # ← Környezeti változók
│
├── .env                       # Root env (API kulcsok)
└── start.sh                   # Indító script
```

## Replikáció lépései (checklist)

Amikor új iparágra készítünk webapp-ot:

### 1. Adatbázis (`webapp/supabase/schema.sql`)
- [ ] Új táblák definiálása az iparágnak megfelelően
- [ ] Enum típusok cseréje (service_type, building_type, stb.)
- [ ] Indexek, triggerek, seed data módosítása

### 2. TypeScript típusok (`webapp/src/lib/types.ts`)
- [ ] Interface-ek a schema.sql tükrözéséhez
- [ ] Union type-ok az enum-okhoz

### 3. Címkék és fordítások (`webapp/src/lib/utils.ts`)
- [ ] Label map-ek cseréje (serviceTypeLabels, buildingTypeLabels, stb.)
- [ ] Formázó funkciók (ha iparág-specifikusak)

### 4. DB lekérdezések (`webapp/src/lib/db/`)
- [ ] Tábla-specifikus query-k (getCompanies → getRestaurants, stb.)
- [ ] Szűrők és keresés módosítása

### 5. Research konfiguráció (`webapp/research_config/`)
- [ ] `items.yaml` — Kutatási témák és kulcsszavak az új iparághoz
- [ ] `prompts/search_prompts.yaml` — Keresési prompt iparágra szabása
- [ ] `prompts/extract_prompts.yaml` — Kinyerési promptok entitástípusonként
- [ ] `schemas/` — Pydantic sémák az új entitásokhoz
- [ ] `mappings/persistence.yaml` — Mező-leképezések az új DB sémához
- [ ] `policies.yaml` — Deduplikáció szabályok (unique_keys, threshold)

### 6. Publikus oldalak (`webapp/src/app/`)
- [ ] Route-ok átnevezése (/cegek → /ettermek, stb.)
- [ ] Oldal szövegek, leírások
- [ ] Kártya és lista komponensek

### 7. Admin konfiguráció (`webapp/src/app/admin/`)
- [ ] `entities/config.ts` — Admin CRUD tábla/mező definíciók
- [ ] Entitás-specifikus merge szabályok

### 8. Környezeti változók
- [ ] `.env.local` — Supabase URL/key
- [ ] `.env` — API kulcsok (Perplexity, stb.)

## Ami NEM változik replikációkor

Ezeket NE módosítsd:
- `research/pipeline/*` — A pipeline lépések általánosak
- `orchestrator/*` — Az ütemező és futtatórendszer
- `db/research_repository.py` — Research repo
- `webapp/src/middleware.ts` — Admin auth middleware
- `webapp/src/app/api/admin/*` — Admin API route-ok (table-name paraméteresek)
- `webapp/src/components/admin/*` — Admin UI komponensek
- `start.sh` — Indító script
