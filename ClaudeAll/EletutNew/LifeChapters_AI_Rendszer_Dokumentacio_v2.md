# Életút AI (LifeChapters AI) — Rendszer Dokumentáció v2.0

> **Típus:** High-level rendszerleírás, fejlesztési alapdokumentum  
> **Cél:** A teljes rendszer megtervezése és kifejlesztése ezen dokumentum alapján  
> **Verzió:** 2.0  
> **Dátum:** 2026. március  
> **Hosting:** Vercel  
> **Platform:** Web alkalmazás (bármilyen eszközön elérhető)

---

## Tartalomjegyzék

1. [Rendszer Áttekintés](#1-rendszer-áttekintés)
2. [Architektúra](#2-architektúra)
3. [Adattárolási modell](#3-adattárolási-modell)
4. [Adatmodell és entitások](#4-adatmodell-és-entitások)
5. [User Journey](#5-user-journey)
6. [AI Backend logika](#6-ai-backend-logika)
7. [Beszélgetési módok és session-kezelés](#7-beszélgetési-módok-és-session-kezelés)
8. [Életút megjelenítés és nézetek](#8-életút-megjelenítés-és-nézetek)
9. [Hang funkciók](#9-hang-funkciók)
10. [Beállítások](#10-beállítások)
11. [Meghívó rendszer és többszereplős logika](#11-meghívó-rendszer-és-többszereplős-logika)
12. [Adatvédelem és biztonság](#12-adatvédelem-és-biztonság)
13. [Állapotjelzők és hibakezelés](#13-állapotjelzők-és-hibakezelés)
14. [Export és mentés](#14-export-és-mentés)
15. [Routing](#15-routing)
16. [Ismert korlátok](#16-ismert-korlátok)

---

## 1. Rendszer Áttekintés

Az Életút AI (LifeChapters AI) egy Vercel-en hostolt webalkalmazás, amely segít a felhasználóknak felépíteni és megőrizni személyes élettörténetüket AI-alapú beszélgetésen keresztül. A rendszer magyar nyelvű, és úgy működik, mint egy empatikus riporter: kérdez, hallgat, és közben automatikusan összegyűjti a ténybeli és érzelmi információkat egy strukturált „életút dokumentumba".

A felhasználó bármilyen eszközről (desktop, tablet, telefon) bejelentkezve folytathatja az életútjának építését — az adatok vagy lokálisan, vagy a rendszer által biztosított biztonságos felhőalapú adatbázisban tárolódnak, a felhasználó döntése szerint.

### 1.1 Alapelvek

- **Adatszuverenitás:** A felhasználó dönti el, hogy adatait lokálisan (saját eszközén) vagy a rendszer által biztosított Supabase-alapú biztonságos felhőben tárolja. Mindkét esetben az adatok kizárólag az övéi.
- **Platformfüggetlenség:** Webalkalmazás, bármilyen modern böngészőből elérhető, bármilyen eszközön. Vercel-en hostolva.
- **Intelligens kérdezés:** A beszélgetés kezdetén a rendszer áttekinti a korábbi beszélgetéseket és a már összeállt életutat, majd ennek alapján dönti el, mely területekről és időszakokról tud keveset — és arra kérdez rá.
- **Szövegközpontú AI:** A rendszer írásban kérdez (nem szükséges hangban válaszolnia), viszont a felhasználó beszélhet is, nem csak gépelhet.
- **Strukturált adatmodell:** Az életút nem csupán szövegblokk, hanem strukturált entitásokból (személyek, helyek, események, időszakok, érzelmek) épül fel.
- **Érzelmi dimenzió:** Nem csak „mi történt", hanem „mit jelentett" — az érzelmek, fontosság és hatás külön rétegként kezelődnek.

---

## 2. Architektúra

### 2.1 Rendszer komponensek

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   React App     │────▶│    Supabase      │────▶│  Edge Function   │
│   (Frontend)    │◀────│  (Auth + opció:  │◀────│  (chat-with-ai)  │
│   Vercel-en     │     │   adattárolás)   │     └──────────────────┘
└─────────────────┘     └──────────────────┘              │
        │                                         ┌───────┴───────┐
        │                                         │   AI API      │
        ▼                                         │  (GPT-4.1+)   │
┌─────────────────┐                               └───────────────┘
│  Lokális tároló  │                                      │
│  (IndexedDB)    │                               ┌───────┴───────┐
│  + titkosítás   │                               │  ElevenLabs   │
└─────────────────┘                               │  (TTS API)    │
                                                  └───────────────┘
```

- **Frontend (React + Vite + TypeScript + Tailwind CSS + shadcn/ui):** A felhasználói felület, Vercel-en hostolva. Kezeli a lokális adattárolást, a chat felületet, a megjelenítést és az összes nézetet.
- **Supabase:** Két szerepben:
  - **Mindig:** Felhasználókezelés (authentikáció, profil adatok)
  - **Opcionálisan:** Teljes adattárolás (ha a felhasználó a felhőalapú tárolást választja)
- **Edge Function (chat-with-ai):** Szerver oldali funkció, amely fogadja a felhasználó üzenetét és a kontextust, majd AI-választ, életút-kinyerést és javaslatokat generál.
- **AI API:** Választható modell (GPT-4.1 mini, GPT-5 stb.)
- **ElevenLabs API:** Szövegfelolvasás, szerver oldali proxy-n keresztül.

### 2.2 Tech Stack

| Réteg | Technológia |
|---|---|
| Frontend | React + Vite + TypeScript + Tailwind CSS + shadcn/ui |
| Hosting | Vercel |
| Authentikáció | Supabase Auth |
| Adatbázis (felhő opció) | Supabase (PostgreSQL + RLS) |
| Adatbázis (lokális opció) | IndexedDB (böngészőben, titkosítva) |
| AI Backend | Supabase Edge Function |
| AI Modell | OpenAI API (GPT-4.1 mini / GPT-5) |
| Szövegfelolvasás | ElevenLabs API (szerver oldali proxy) |
| Hangfelismerés | Web Speech API (böngésző natív) |

---

## 3. Adattárolási modell

### 3.1 A felhasználó választása: lokális vs. felhő

A regisztráció vagy az első beállítás során a felhasználó eldönti, hol tárolja az adatait. Ezt később bármikor megváltoztathatja (migrálással).

| Szempont | Lokális tárolás | Felhő tárolás (Supabase) |
|---|---|---|
| **Hol vannak az adatok?** | A felhasználó böngészőjében (IndexedDB) | Supabase szerveren, titkosítva |
| **Több eszközön elérhető?** | Nem (export/import szükséges) | Igen, bármely eszközön bejelentkezve |
| **Automatikus backup** | Nem (manuális export) | Igen |
| **Adatszuverenitás** | Teljes — semmi nem hagyja el az eszközt | A rendszer kezeli, de a user tulajdona |
| **Titkosítás** | Lokális titkosítás (passphrase) | Supabase RLS + szerver oldali titkosítás |
| **Eszközváltás** | Export/import fájllal | Automatikus szinkron |

### 3.2 Supabase — mindig használt táblák (user management)

| Tábla | Cél |
|---|---|
| `profiles` | Felhasználói profil (display_name, storage_preference, privacy_accepted_at) |

### 3.3 Supabase — felhő tárolás esetén használt táblák

| Tábla | Cél |
|---|---|
| `chat_sessions` | Chat munkamenetek (user_id, title, mode, goal, timestamps) |
| `messages` | Egyéni chat üzenetek (session_id, user_id, content, is_user, draft) |
| `life_stories` | Az összegyűjtött életút dokumentum (user_id, content, title) |
| `persons` | Személyek entitás-tábla (lásd 4.2) |
| `events` | Események entitás-tábla (lásd 4.3) |
| `locations` | Helyszínek entitás-tábla (lásd 4.4) |
| `time_periods` | Időszakok entitás-tábla (lásd 4.5) |
| `emotions` | Érzelmi réteg (lásd 4.6) |
| `open_questions` | Nyitott kérdések, félbehagyott pontok (lásd 4.7) |
| `invitations` | Meghívók kezelése |
| `invitation_contributions` | Meghívottak hozzájárulásai (jóváhagyásra váró) |

### 3.4 Lokális tárolás esetén

Ugyanezek az adatstruktúrák IndexedDB-ben tárolódnak, JSON formátumban, titkosítva. A séma megegyezik a felhő változattal, hogy a migráció egyszerű legyen.

---

## 4. Adatmodell és entitások

Az életút nem csupán szövegblokk, hanem strukturált entitásokból épül fel. Ez lehetővé teszi az intelligens keresést, összekapcsolást, és a különböző nézeteket.

### 4.1 Életút dokumentum (life_stories)

| Mező | Típus | Leírás |
|---|---|---|
| id | UUID | Egyedi azonosító |
| user_id | UUID | Tulajdonos |
| content | TEXT | Az összegyűjtött szöveges életút (markdown) |
| title | TEXT | Az életút címe |
| last_updated | TIMESTAMP | Utolsó frissítés |

### 4.2 Személyek (persons)

Minden az életútban említett személy külön entitásként kezelendő.

| Mező | Típus | Leírás |
|---|---|---|
| id | UUID | Egyedi azonosító |
| user_id | UUID | Tulajdonos |
| name | TEXT | Teljes név |
| nickname | TEXT | Becenév (opcionális) |
| relationship_type | TEXT | Kapcsolat típusa (szülő, testvér, barát, kolléga, partner, tanár, stb.) |
| related_period | TEXT | Kapcsolódó időszak (pl. „1990–1998", „általános iskola") |
| related_event_ids | UUID[] | Hozzá kötődő események |
| notes | TEXT | Megjegyzések, pontosítások |
| uncertainty | TEXT | Bizonytalanságok (pl. „nem biztos a vezetéknév") |
| created_at | TIMESTAMP | Létrehozás |
| updated_at | TIMESTAMP | Utolsó frissítés |

### 4.3 Események (events)

| Mező | Típus | Leírás |
|---|---|---|
| id | UUID | Egyedi azonosító |
| user_id | UUID | Tulajdonos |
| title | TEXT | Esemény rövid neve |
| description | TEXT | Részletes leírás |
| time_type | ENUM | `exact_date`, `estimated_year`, `life_phase`, `uncertain` |
| exact_date | DATE | Pontos dátum (ha van) |
| estimated_year | INT | Becsült év (ha van) |
| life_phase | TEXT | Életszakasz (pl. „általános iskola", „első munkahelyem idején") |
| uncertain_time | TEXT | Bizonytalan időjelölés (pl. „kb. 1998", „talán nyáron") |
| location_id | UUID | Kapcsolódó helyszín |
| person_ids | UUID[] | Kapcsolódó személyek |
| category | TEXT | Kategória (család, tanulmányok, munka, barátok, hobbi, utazás, fordulópont, stb.) |
| is_turning_point | BOOLEAN | Fordulópont-e az életben |
| source | ENUM | `self`, `invited_person` (ki adta meg) |
| created_at | TIMESTAMP | Létrehozás |

### 4.4 Helyszínek (locations)

| Mező | Típus | Leírás |
|---|---|---|
| id | UUID | Egyedi azonosító |
| user_id | UUID | Tulajdonos |
| name | TEXT | Helyszín neve (pl. „Budapest, XIII. kerület") |
| type | TEXT | Típus (város, iskola, munkahely, lakóhely, nyaralóhely stb.) |
| related_period | TEXT | Kapcsolódó időszak |
| coordinates | JSON | Opcionális: GPS koordináták (térkép nézethez) |
| notes | TEXT | Megjegyzések |

### 4.5 Időszakok (time_periods)

| Mező | Típus | Leírás |
|---|---|---|
| id | UUID | Egyedi azonosító |
| user_id | UUID | Tulajdonos |
| label | TEXT | Megnevezés (pl. „Általános iskola", „Első munkahelyem") |
| start_type | ENUM | `exact`, `estimated`, `uncertain` |
| start_value | TEXT | Kezdet (pl. „1990", „kb. 1988") |
| end_type | ENUM | `exact`, `estimated`, `uncertain`, `ongoing` |
| end_value | TEXT | Vég (pl. „1998", „talán 2002", null ha ongoing) |
| category | TEXT | Kategória |
| event_ids | UUID[] | Kapcsolódó események |
| person_ids | UUID[] | Kapcsolódó személyek |

### 4.6 Érzelmi réteg (emotions)

Az érzelmek külön, opcionális rétegként kezelendők — nem csak „mi történt", hanem „mit jelentett".

| Mező | Típus | Leírás |
|---|---|---|
| id | UUID | Egyedi azonosító |
| user_id | UUID | Tulajdonos |
| event_id | UUID | Kapcsolódó esemény |
| feeling | TEXT | Milyen érzés kapcsolódott hozzá (szabad szöveg) |
| valence | ENUM | `positive`, `negative`, `mixed`, `neutral` |
| importance | INT | Mennyire volt fontos (1–5 skála) |
| long_term_impact | TEXT | Későbbi hatása az életre (opcionális) |
| notes | TEXT | Egyéb megjegyzés |

### 4.7 Nyitott kérdések (open_questions)

A rendszer nyilvántartja, mely pontok maradtak félbehagyva vagy tisztázatlanok.

| Mező | Típus | Leírás |
|---|---|---|
| id | UUID | Egyedi azonosító |
| user_id | UUID | Tulajdonos |
| question_type | ENUM | `incomplete_topic`, `unresolved_event`, `unclear_time`, `missing_detail`, `follow_up` |
| description | TEXT | Mi maradt nyitva |
| related_event_id | UUID | Kapcsolódó esemény (opcionális) |
| related_person_id | UUID | Kapcsolódó személy (opcionális) |
| priority | INT | Fontosság (1–5) |
| status | ENUM | `open`, `addressed`, `closed` |
| created_at | TIMESTAMP | Létrehozás |
| addressed_at | TIMESTAMP | Mikor lett kezelve |

### 4.8 Idővonal-bizonytalanság kezelése

Az életút-emlékek ritkán rendelkeznek pontos dátummal. A rendszer négyféle időjelölést kezel:

| Típus | Példa | Kezelés |
|---|---|---|
| **Pontos dátum** | „1995. szeptember 1." | Dátum mezőben tárolva, idővonalra pontosan elhelyezve |
| **Becsült év** | „kb. 1998" | Év mezőben tárolva, idővonalra becsült helyre téve, vizuálisan jelölve |
| **Életszakasz alapú** | „általános iskola alatt", „az első munkahelyem idején" | Kapcsolt time_period entitáshoz kötve, annak időkeretén belül elhelyezve |
| **Bizonytalan** | „talán nyáron", „valamikor a 90-es években" | Szabad szöveges időjelölés, idővonalra hozzávetőlegesen elhelyezve, kérdőjellel jelölve |

Az AI soha nem „pontosít" agresszíven — ha a felhasználó bizonytalanul emlékszik, a rendszer elfogadja és rögzíti a bizonytalanságot is. Később visszakérdezhet finoman, de nem erőlteti.

---

## 5. User Journey

### 5.1 Első használat — Onboarding

Az első bejelentkezéskor a felhasználó nem csak egy üdvözlő képernyőt lát, hanem irányított bevezetést kap:

1. **Üdvözlés és bemutatkozás:** Mi ez az alkalmazás, mire való
2. **Hogyan működik:** Az AI kérdez, a felhasználó mesél — szöveggel vagy hanggal
3. **Mire számítson:** Az AI empatikus és türelmes, nem siettet, bármilyen részletességgel lehet mesélni
4. **Adattárolás választása:** Lokális (eszközön marad minden) VAGY felhőalapú (bármely eszközön elérhető)
5. **Lokális titkosítás beállítása** (ha lokálisat választ): Passphrase megadása
6. **Hogyan javíthat:** Az életutat bármikor szerkesztheti, pontosíthatja
7. **Hogyan készítsen mentést:** Export funkció bemutatása
8. „**Kezdjük el!**" gomb → az első beszélgetés indul

### 5.2 Regisztráció / Bejelentkezés

1. A felhasználó megnyitja az alkalmazást (Vercel URL)
2. Ha nincs bejelentkezve, átirányítódik az auth oldalra
3. Email + jelszó alapú regisztráció vagy bejelentkezés (Supabase Auth)
4. Regisztráció után email megerősítés szükséges
5. Sikeres bejelentkezés után → onboarding (új user) VAGY főoldal (visszatérő user)

### 5.3 Chat Felület (fő képernyő)

A felhasználó itt beszélget az AI-val. Ez az alkalmazás központi eleme.

**Működési folyamat:**

1. Betöltéskor a rendszer betölti a korábbi üzeneteket (lokálisból vagy Supabase-ből, a beállítástól függően)
2. **Kontextus-elemzés:** A rendszer áttekinti a már meglévő életutat, a korábbi beszélgetéseket, a nyitott kérdéseket, és meghatározza:
   - Mely területekről (család, tanulmányok, munka, barátok, hobbi, utazások stb.) tud keveset
   - Mely időszakok hiányoznak vagy alulreprezentáltak
   - Mely nyitott kérdések várnak tisztázásra
3. Ha nincs korábbi üzenet, megjelenik az üdvözlő üzenet magyarul
4. A felhasználó ír vagy diktál egy üzenetet
5. Az üzenet azonnal mentésre kerül (draft-ként is, a véletlen adatvesztés ellen)
6. A rendszer elküldi az üzenetet + kontextust az AI backend-nek
7. Az AI válasz megjelenik gépelő-animációval
8. Megjelennek javaslat-chipek (ha be van kapcsolva)

### 5.4 Session közbeni piszkozatmentés

- Minden üzenet beírás közben automatikusan draft-ként mentődik
- Ha a böngésző bezáródik, a draft megmarad
- Következő megnyitáskor a rendszer felajánlja a félbemaradt üzenet helyreállítását
- A session állapota is mentődik (hol tartott a beszélgetés, milyen módban volt)

---

## 6. AI Backend logika

### 6.1 Általános működés

Egyetlen Edge Function (chat-with-ai) kezeli a teljes AI logikát. Minden felhasználói üzenet után párhuzamos AI hívások történnek:

### 6.2 Intelligens kérdezés (fő válasz)

- **Modell:** Választható (GPT-4.1 mini, GPT-5 stb.)
- Az utolsó ~20 üzenetet kapja kontextusként
- Megkapja a jelenlegi életút dokumentumot
- Megkapja a nyitott kérdések listáját
- Megkapja az aktuális session módját és célját (lásd 7. fejezet)
- **A válasz előtt elemzi:**
  - Mely életterületek hiányoznak vagy alulreprezentáltak
  - Mely időszakokról nincs információ
  - Mely nyitott kérdések a legfontosabbak
  - Mit kérdezett már — és ne kérdezze újra túl hamar
- Ennek alapján fogalmazza meg a következő kérdés(eke)t
- Egyszerre egy témára fókuszál
- **A rendszernek nem kell szóban válaszolnia — elegendő, ha kiírja a kérdéseket**

### 6.3 Ismétlődés-elkerülés

Az AI a kérdésfeltevésnél betartja a következő szabályokat:

- Ne kérdezze újra túl gyakran ugyanazt a témát
- Ismerje fel, ha egy témát már eléggé feltárt (elég részlet van róla az életútban)
- Tudja, mikor kell természetesen témát váltani
- Ha a felhasználó kitérő választ ad egy témára, ne erőltesse — térjen vissza rá később, finoman
- A nyitott kérdések listáját használja annak eldöntésére, hol érdemes folytatni

### 6.4 Életút kinyerés (párhuzamos hívás)

- Kivonja a felhasználó üzeneteiből a ténybeli információkat
- Azonosítja és létrehozza/frissíti a strukturált entitásokat:
  - **Személyek:** nevek, becenevek, kapcsolat típusa
  - **Események:** mi történt, mikor, hol, kivel
  - **Helyszínek:** hol játszódott
  - **Időszakok:** mikor, milyen bizonytalansággal
  - **Érzelmek:** milyen érzés kapcsolódott hozzá (ha a felhasználó említi)
- Évek/időszakok és területek szerint rendezi
- **Csak** a felhasználó által mondott tényeket rögzíti, az AI kérdéseit nem
- Ha nincs új információ: nem frissít
- Automatikusan frissíti a lokálisan vagy felhőben tárolt életút dokumentumot és entitásokat
- Felismeri és rögzíti az idővonal-bizonytalanságokat (pontos dátum / becsült év / életszakasz / bizonytalan)

### 6.5 Érzelmi réteg kinyerés (párhuzamos)

- Ha a felhasználó érzelmet, fontosságot vagy hatást említ egy eseményhez kapcsolódóan, a rendszer ezt külön rögzíti
- Automatikusan megpróbálja besorolni: pozitív / negatív / vegyes / semleges
- Fontossági szintet becsül (1–5)
- Ha a felhasználó említi a hosszú távú hatást („ez megváltoztatta az életemet"), azt is rögzíti
- Ez az egész opcionális réteg — ha a felhasználó csak tényeket mond, nem erőlteti az érzelmeket

### 6.6 Javaslat-generálás (párhuzamos)

- 3 rövid, konkrét folytatási javaslatot generál (max 8 szó)
- A javaslatok a hiányos területekre és nyitott kérdésekre fókuszálnak
- Változatos témaköröket fednek le
- A frontenden kattintható chipekként jelennek meg
- **Kikapcsolható** a beállításokban

### 6.7 Nyitott kérdések frissítése (párhuzamos)

- Minden üzenet után frissíti a nyitott kérdések listáját:
  - Új nyitott kérdéseket ad hozzá (félbehagyott témák, bizonytalan időpontok, hiányzó részletek)
  - Lezárja azokat, amelyekre már választ kapott
  - Priorizálja a fennmaradókat

---

## 7. Beszélgetési módok és session-kezelés

### 7.1 Beszélgetési módok

A felhasználó választhat, milyen stílusban szeretne beszélgetni. Az AI ennek megfelelően viselkedik.

| Mód | Leírás | AI viselkedés |
|---|---|---|
| **Szabad mesélés** | A felhasználó szabadon mesél, az AI hallgat és kérdez | Minimális irányítás, nyitott kérdések, a felhasználó vezet |
| **Célzott interjú** | Strukturált kérdéssor egy adott témáról | Az AI fókuszáltan kérdez, mélyebb részleteket keres |
| **Idővonal-építés** | Kronologikus haladás az élet mentén | Az AI időrendben halad, hiányokat keres az idővonalban |
| **Családi kapcsolatok feltárása** | Családtagok, rokoni kapcsolatok, dinamikák | Az AI a személyekre és kapcsolatokra fókuszál |
| **Karrierinterjú** | Munkahelyek, szakmai fejlődés, döntések | Az AI a szakmai pályára koncentrál |

### 7.2 Session-cél beállítása

Minden új session elején a felhasználó kiválaszthatja (opcionálisan), mire szeretne fókuszálni:

- Gyerekkor
- Család
- Munka és karrier
- Iskolák, tanulmányok
- Kapcsolatok (barátok, partnerek)
- Utazások
- Nehéz időszakok
- Kedves emlékek
- Fordulópontok
- Szabad (nincs konkrét cél)

Ha a felhasználó nem választ célt, a rendszer az intelligens hiányfelismerés alapján dönt, mire kérdezzen.

### 7.3 Session-kezelés

- Új session indítása bármikor
- Régi session-ök listázása és folytatása
- Session törlése (megerősítéssel)
- Session-ök automatikus elnevezése a tartalom alapján
- Az aktuális session állapota (mód, cél, hol tartunk) mindig mentésre kerül

---

## 8. Életút megjelenítés és nézetek

### 8.1 Életút nézet (fő)

- Elérhető az „Életút" gombbal a chat headerből
- Megjeleníti az összegyűjtött életút dokumentumot — az AI által automatikusan összegyűjtött információkat
- Területek szerint is böngészhető (család, iskola, munka stb.)
- **Szerkeszthető:** A felhasználó manuálisan javíthatja, kiegészítheti, törölheti az információkat

### 8.2 Idővonal nézet

- Klasszikus vizuális idővonal az élet mentén
- Az események az idővonal-bizonytalanság típusa szerint különböző vizuális jelölést kapnak:
  - Pontos dátum: fix pont
  - Becsült év: halvány pont
  - Életszakasz: sáv
  - Bizonytalan: kérdőjeles, szaggatott jelölés
- Szűrhető kategóriák szerint
- Kattintásra megnyílik az esemény részlete

### 8.3 Térkép nézet

- Helyszínek megjelenítése térképen
- Az életút földrajzi dimenziója — hol élt, hol járt, hol dolgozott
- Kattintásra megjelennek a kapcsolódó események és időszakok

### 8.4 Személykapcsolati nézet

- Vizuális megjelenítés az életútban szereplő személyekről és kapcsolataikról
- Ki kicsoda, milyen kapcsolatban áll a felhasználóval
- Kattintásra megjelennek a kapcsolódó események és időszakok

---

## 9. Hang funkciók

### 9.1 Szövegfelolvasás (TTS — ElevenLabs)

- A felhasználó be/kikapcsolhatja a hangszóró gombot
- Ha bekapcsolt, az AI válasza automatikusan felolvasásra kerül
- Motor: ElevenLabs API, **szerver oldali proxy-n keresztül** (az API kulcs nem kerül a kliensre)
- Választható férfi és női hang
- Választható TTS modell (Eleven v3, Turbo v2.5, Multilingual v2)
- Sebesség állítható: 0.7x – 1.5x
- Mondatonként darabolja a szöveget és egymás után játssza le

### 9.2 Hangfelismerés (STT — Web Speech API)

- A felhasználó be/kikapcsolhatja a mikrofon gombot
- Bekapcsolt állapotban megjelenik a mikrofon gomb az input mezőben
- Magyar nyelvű felismerés (hu-HU)
- Az átírt szöveg automatikusan elküldődik üzenetként
- Vizuális feedback: pulzáló piros jelző + hullámforma animáció

---

## 10. Beállítások

A felhasználó a headerből elérhető Beállítások menüben konfigurálhatja:

| Beállítás | Értékek | Mentés |
|---|---|---|
| **Adattárolás helye** | Lokális / Felhő (Supabase) | Profil (Supabase) |
| Chat AI modell | GPT-4.1 mini, GPT-5 stb. | Lokális |
| TTS modell | Eleven v3, Turbo v2.5, Multilingual v2 | Lokális |
| Hang (férfi/női) | 2 ElevenLabs voice ID | Lokális |
| Felolvasási sebesség | 0.7x – 1.5x | Lokális |
| **Témajavaslatok (Topic Hints)** | Be / Ki | Lokális |
| **Érzelmi réteg rögzítése** | Be / Ki | Lokális |
| **Lokális titkosítás passphrase** | Módosítható | Lokálisan, titkosítva |

Mobilon Drawer, desktopon Popover formában jelenik meg.

---

## 11. Meghívó rendszer és többszereplős logika

### 11.1 Meghívás

A felhasználó meghívhat családtagokat, barátokat, akik hozzáadhatják saját perspektívájukat az életúthoz.

- Meghívó generálása (link vagy email)
- A meghívott regisztrál és hozzáfér a megosztott felülethez
- A meghívott csak a számára engedélyezett műveleteket végezheti

### 11.2 Jogosultsági szintek

| Szint | Mit tehet |
|---|---|
| **Csak olvasó** | Megtekintheti az életutat (vagy annak megosztott részeit) |
| **Kommentelő** | Olvashat + megjegyzéseket fűzhet eseményekhez |
| **Saját emléket hozzáadó** | Saját emlékeket, perspektívákat adhat hozzá (jóváhagyásra vár) |
| **Szerkesztő** | Javíthat meglévő bejegyzéseket (jóváhagyásra vár) |
| **Időkorlátos hozzáférés** | Bármely fenti szint, de lejárati dátummal |

### 11.3 Perspektívák elkülönítése

Ha külső személyek is hozzáadnak tartalmat, ezt tisztán el kell választani:

| Perspektíva típus | Jelölés | Kezelés |
|---|---|---|
| **Saját emlékem** | Alapértelmezett, nincs külön jelölés | Az életút fő része |
| **Más emléke rólam** | „[Személy neve] emléke" badge | Külön jelölve, de integrálva |
| **Közös esemény** | „Közös emlék" badge | Mindkét perspektíva megjelenik |
| **Vitatott emlék** | „Eltérő emlékek" badge | Mindkét verzió megmarad, nincs „igazság" eldöntése |

### 11.4 Jóváhagyási workflow

A külső személy által hozzáadott tartalom **nem** kerül automatikusan be az életút fő dokumentumba:

1. A meghívott személy beírja az emlékét / módosítását
2. A tartalom „jóváhagyásra vár" státuszba kerül
3. Az életút tulajdonosa értesítést kap
4. A tulajdonos megtekinti a hozzájárulást
5. Döntés: **elfogadás** (bekerül az életútba, forrással jelölve) / **elutasítás** (nem kerül be, de megmarad az archívumban) / **módosítás után elfogadás**
6. A hozzájárulás forrása (ki adta) mindig megmarad

---

## 12. Adatvédelem és biztonság

### 12.1 Authentikáció

- Supabase Auth (email + jelszó)
- Persistent session, automatikus token frissítés
- Email megerősítés regisztrációkor

### 12.2 Adatbázis biztonság (felhő opció)

- Row Level Security (RLS) minden Supabase táblán
- A felhasználó csak a saját adataihoz fér hozzá
- A meghívottak csak a számukra engedélyezett adatokhoz férnek hozzá

### 12.3 Lokális titkosítás (lokális opció)

Mivel érzékeny életút-adatokról van szó, a lokális tárolás esetén:

- **Titkosítás:** Az IndexedDB-ben tárolt adatok titkosítva vannak (AES-256 vagy hasonló)
- **Passphrase:** A felhasználó saját passphrase-t állít be, amely nélkül az adatok nem olvashatóak
- **Automatikus zárolás:** Beállítható idő inaktivitás után a rendszer automatikusan zárol (pl. 15 perc)
- **Újbóli belépés:** Zárolás után a passphrase újbóli megadása szükséges
- A passphrase **nem** tárolódik szerveren — ha a felhasználó elfelejti, az adatok nem visszaállíthatóak (erről figyelmeztetés az onboarding során)

### 12.4 API kulcsok

- **OpenAI API kulcs:** Szerver oldalon (Edge Function env), biztonságos
- **ElevenLabs API kulcs:** Szerver oldalon (Edge Function env), proxy-n keresztül — **nem** a kliens oldalon
- A frontend nem tartalmaz érzékeny API kulcsokat

### 12.5 Adatminimalizálás

- Az AI backend csak a szükséges kontextust kapja meg (utolsó ~20 üzenet + életút kivonat)
- A teljes chat történet nem hagyja el az eszközt / a felhasználó adattárhelyét
- A Supabase (user management módban) nem tárol személyes életút-adatokat

---

## 13. Állapotjelzők és hibakezelés

### 13.1 Státusz jelzők

A header jobb felső sarkában állapotjelzők látszanak:

| Jelző | Zöld | Szürke | Piros (pulzáló) |
|---|---|---|---|
| **AI** | Elérhető, működik | Nem tesztelt | Hiba vagy nem elérhető |
| **Hang** | ElevenLabs elérhető | Nem aktív | Hiba / kvóta kimerült |
| **Tárolás** | Szinkronban | — | Szinkronizációs hiba |

Tooltip-ben részletes hibaüzenet jelenik meg hiba esetén.

### 13.2 Hibakezelés

- Hálózati hiba esetén a rendszer lokálisan tárolja az üzenetet és újrapróbálja
- AI hiba esetén hibaüzenet + újrapróbálás gomb
- Szinkronizációs hiba (felhő mód) esetén az adatok lokálisan megmaradnak és a következő sikeres kapcsolatkor szinkronizálódnak

---

## 14. Export és mentés

### 14.1 Életút exportálás

A felhasználó letöltheti az életút dokumentumot:

| Formátum | Tartalom |
|---|---|
| **PDF** | Formázott életút dokumentum, idővonallal |
| **DOCX** | Szerkeszthető Word dokumentum |
| **JSON** | Teljes strukturált adat (személyek, események, helyek, érzelmek — backup célra) |

### 14.2 Adatmentés és visszaállítás

- **Teljes backup:** Az összes adat (beszélgetések, életút, entitások, beállítások) exportálása egyetlen titkosított fájlba
- **Visszaállítás:** A backup fájl importálása másik eszközön vagy böngészőben
- **Felhő → Lokális migráció:** Az adatok letöltése a felhőből és lokális tárolásra váltás
- **Lokális → Felhő migráció:** A lokális adatok feltöltése a felhőbe

---

## 15. Routing

| Útvonal | Komponens | Cél |
|---|---|---|
| `/` | Index | Fő oldal (Onboarding → Chat → Életút nézetek) |
| `/auth` | Auth | Bejelentkezés / Regisztráció |
| `/settings` | Settings | Beállítások (opcionálisan külön route) |
| `*` | NotFound | 404 oldal |

Az Index oldal belső állapotkezelésen keresztül vált a nézetek (chat, életút, idővonal, térkép, személyek) között, nem külön route-okon.

---

## 16. Ismert korlátok

1. **Lokális tárolás** esetén az adatok az adott eszköz adott böngészőjéhez kötöttek — eszközváltáshoz export/import szükséges
2. A böngésző lokális tárhelyének mérete korlátozott (általában ~50–100 MB)
3. A **SpeechRecognition API** böngészőfüggő (Chrome-ban a legjobb, Safari és Firefox korlátozott)
4. Az AI válasz minősége függ a választott modelltől és a kontextus méretétől
5. A **passphrase elvesztése** lokális titkosítás esetén az adatok végleges elvesztését jelenti
6. A **térkép nézet** csak akkor működik jól, ha a felhasználó viszonylag konkrét helyszíneket említ
7. A **többszereplős funkciók** (meghívók, perspektívák) csak felhő tárolás esetén érhetőek el
8. Az offline működés korlátozott — az AI válaszokhoz internetkapcsolat szükséges

---

## Összefoglaló: Mit csinál a rendszer?

> Az Életút AI egy empatikus, intelligens beszélgetőtárs, amely segít az embereknek megírni az élettörténetüket. Kérdez, hallgat, és közben automatikusan felépít egy strukturált életút-dokumentumot — személyekkel, eseményekkel, helyszínekkel, időszakokkal és érzelmekkel. Az adatok a felhasználó döntése szerint az eszközén vagy biztonságos felhőben tárolódnak. Családtagok és barátok meghívhatóak, hogy saját perspektívájukkal gazdagítsák a történetet. Az eredmény bármikor exportálható, szerkeszthető és megosztható.
