# Document Insight Service

REST API (FastAPI) koji prima PDF dokumente i slike (PNG/JPG), izvlači iz njih tekst i tablice (skenove čita OCR-om)
i odgovara na pitanja o njihovom sadržaju. Koristi RAG pristup: semantičko pretraživanje (FAISS) pronalazi relevantne
dijelove dokumenata, a model za question answering (RoBERTa SQuAD2) iz njih izvlači odgovor. Uz API dolazi i Streamlit UI,
a cijela aplikacija se pokreće jednom naredbom kroz Docker.

## Što servis radi

1. `POST /upload`: prima jedan ili više PDF-ova ili slika (PNG/JPG), izvlači tekst i tablice (OCR za skenove), dijeli ih
   u chunkove i gradi FAISS indeks. Dokumenti se grupiraju u **sesiju**.
2. `POST /ask`: prima pitanje i pretražuje jedan dokument ili sve dokumente sesije. Vraća odgovor i **izvor** (ime
   datoteke, stranica i tekst chunka iz kojeg je odgovor izvučen).
3. `GET /documents`: popis učitanih dokumenata (opcionalno filtriran po sesiji).
4. `DELETE /sessions/{id}`: briše sesiju i njezine dokumente iz memorije.

## Tehnologije i zašto

| Dio | Alat | Zašto |
|---|---|---|
| API | **FastAPI** | Brz razvoj, validacija zahtjeva (Pydantic), automatska dokumentacija na `/docs`. |
| Ekstrakcija teksta | **PyMuPDF** | Brza i točna za PDF-ove s tekstualnim slojem; ima detekciju tablica, pa se retci tablica mogu tretirati posebno. |
| OCR | **EasyOCR** | Prepoznaje tekst na slikama i skeniranim stranicama; radi lokalno na CPU-u, bez vanjskog API-ja, a modeli se ugrađuju u Docker image. |
| Embeddingi | **sentence-transformers `all-MiniLM-L6-v2`** | Mali model (brz na CPU-u) s dobrom semantičkom kvalitetom za pretragu. |
| Vektorska pretraga | **FAISS** (`IndexFlatIP`) | Egzaktna pretraga po kosinusnoj sličnosti (normalizirani vektori); za ovu veličinu dokumenata je dovoljno brza i bez dodatne infrastrukture. |
| QA model | **`deepset/roberta-base-squad2`** (Hugging Face Transformers) | Extractive QA: odgovor je dio teksta iz dokumenta, pa je provjerljiv i ne "halucinira". Radi lokalno, bez API ključa. |
| UI | **Streamlit** | Najbrži način da se tok upload → pitanje → izvor pokaže u pregledniku. |
| Testovi | **pytest** + FastAPI `TestClient` | Brzi API testovi bez pokretanja servera. |
| CI | **GitHub Actions** | Pokreće pytest na svaki push i pull request. |
| Pakiranje | **Docker + docker-compose** | Backend i UI kao dva servisa, modeli ugrađeni u image. |

**Napomena o QA modelu:** SQuAD2 modeli mogu prepoznati da u tekstu nema odgovora (opcija `handle_impossible_answer`).
Isprobali smo to, ali su odgovori s uključenom opcijom ispadali lošiji, pa **nije uključeno**. Umjesto toga, pouzdanost
se rješava transparentnošću: uz svaki odgovor vraća se i **chunk iz kojeg je odgovor došao** (datoteka, stranica, tekst),
pa korisnik, ako nije siguran, može sam provjeriti podatak u izvoru.

### Kako to radi (RAG tok)

```
Dokument → PyMuPDF (tekst + tablice) ili EasyOCR (skenovi, slike)
         → chunkovi (180 riječi, preklapanje 35)
         → MiniLM embeddingi → FAISS indeks (po dokumentu)

Pitanje → embedding → FAISS top-5 chunkova po dokumentu
        → RoBERTa QA nad svakim chunkom → odgovor s najvećom pouzdanošću + chunk-izvor
```

- **Tablice** se pretvaraju u tekst "jedna rečenica po retku" i indeksiraju kao zasebni chunkovi. U trenutku pitanja
  QA modelu se daje samo redak tablice koji je najsličniji pitanju (`select_best_row`).
- **Sesija:** kod pitanja nad sesijom dohvat se radi zasebno u svakom dokumentu, svi kandidati idu u isti QA krug i
  pobjeđuje onaj s najvećom QA pouzdanošću (sličnost dohvaćanja je dodatni kriterij kod izjednačenja).
- Modeli se učitavaju **lijeno**, pri prvom pitanju ili uploadu, pa prvi zahtjev lokalno traje duže.

## Struktura projekta

```
app/
  main.py           API rute (/upload, /ask, /documents, /sessions)
  schemas.py        Pydantic modeli zahtjeva
  state.py          spremanje dokumenata i sesija u memoriji
  config.py         konstante (limiti, veličina chunka, top-k, OCR postavke)
  pdf_processor.py  ekstrakcija teksta i tablica (PyMuPDF), OCR fallback za skenirane stranice
  ocr.py            EasyOCR (lijeno učitavanje), priprema slika
  files.py          provjera tipa datoteke (magic bytes), čišćenje imena datoteke
  chunking.py       dijeljenje u chunkove
  retrieval.py      embeddingi, FAISS, odabir retka tablice
  models.py, qa.py  lijeno učitavanje modela
frontend/streamlit_app.py       Streamlit UI
sample_docs/                    testni PDF-ovi i slike
tests/                          pytest testovi i skupovi pitanja za evaluaciju (first/second/third batch)
scripts/evaluate_documents.py   evaluacija kvalitete odgovora
scripts/download_models.py      skida modele pri Docker buildu
Dockerfile.backend, Dockerfile.frontend, docker-compose.yml, docker-compose.dev.yml
.github/workflows/test.yaml     CI
```

## Pokretanje

### Docker (preporučeno)

Potreban je samo Docker Desktop (Python i biblioteke nisu potrebni). Iz mape projekta:

```bash
docker compose up --build
```

- UI: http://localhost:8501
- API i dokumentacija: http://localhost:8000/docs

Prvi build traje dulje jer instalira CPU verziju torch-a i ugrađuje Hugging Face i EasyOCR modele u image
(zato prvi zahtjev nije spor i kontejner radi bez interneta). Sljedeći buildovi koriste cache slojeva, pa promjena koda
traje sekunde. Nakon `git pull` uvijek pokreni s `--build`, inače se koristi stari image. Zaustavljanje: `Ctrl+C` ili
`docker compose down`.

Razvoj bez ponovnog builda (kod se montira u kontejner, uvicorn radi s `--reload`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### Ručna instalacija

Potreban je Python 3.13 (isti kao u CI-ju). Iz mape projekta:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-ui.txt
```

(Linux/macOS: `source .venv/bin/activate`, pa `pip install -r requirements-dev.txt -r requirements-ui.txt`.)

Prvo pokretanje skida modele (Hugging Face, EasyOCR; ukupno nekoliko stotina MB), pa treba internet.

Zavisnosti su podijeljene: `requirements.txt` (backend), `requirements-ui.txt` (Streamlit), `requirements-dev.txt`
(backend + testovi).

**Backend:**

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

API je na http://127.0.0.1:8000, a interaktivna dokumentacija na http://127.0.0.1:8000/docs.

**Frontend (Streamlit)**, u drugom terminalu, dok backend radi:

```powershell
.venv\Scripts\streamlit.exe run frontend/streamlit_app.py
```

UI je na http://localhost:8501. URL backenda može se promijeniti u sidebaru.

U UI-ju možeš odabrati više PDF-ova ili slika odjednom, postavljati pitanja nad cijelom sesijom ili jednim dokumentom,
vidjeti izvor odgovora (datoteka, stranica i tekst) te obrisati sesiju.

> **Napomena o Swagger UI-ju:** polje `files` u `/docs` prikazuje se kao `array<string>` i ne nudi odabir datoteka
> (ograničenje Swaggera s OpenAPI 3.1). Za više datoteka koristi curl, Python ili Streamlit UI.

## Slike i OCR

- Podržani formati: **PDF, PNG, JPG/JPEG**. Tip se određuje po **sadržaju** (magic bytes), ne samo po ekstenziji:
  datoteka `lazna.png` koja nije slika odbija se s 400.
- **PDF:** stranice s tekstualnim slojem čita PyMuPDF (brzo, s tablicama). Stranice **bez** teksta (skenovi) renderiraju
  se u sliku (200 dpi) i čita ih EasyOCR.
- **Slike:** dekodiraju se (prozirnost i CMYK se uklanjaju, velike se smanjuju na 3000 px), pa ih čita EasyOCR;
  slika postaje dokument s jednom stranicom.
- **Imena datoteka** se čiste prije spremanja i prikaza (bez putanja i posebnih znakova, najviše 100 znakova), pa
  `../../x<y>.png` postaje `x_y_.png`.
- EasyOCR se učitava **lijeno** (pri prvom OCR-u). Lokalno pri prvom pokretanju skida modele (~100 MB) u `~/.EasyOCR`;
  u Dockeru su ugrađeni u image.
- Skenirani primjeri su u `sample_docs/`.

## Testovi i evaluacija

```powershell
.venv\Scripts\python.exe -m pytest -v                       # unit/API testovi, brzi, bez pravih modela
.venv\Scripts\python.exe scripts/evaluate_documents.py      # evaluacija kvalitete s pravim modelima, sporije
```

- **pytest** provjerava ispravnost koda (validacija zahtjeva, sesije, brisanje, odabir odgovora). Retrieval i QA model su
  u tim testovima lažirani, pa oni ne mjere kvalitetu odgovora. CI ih pokreće na svaki push.
- **Evaluacija kvalitete** koristi prave modele i tri skupa pitanja s očekivanim odgovorima nad dokumentima iz `sample_docs/`:

  | Skup | Datoteka | Pitanja |
  |---|---|---|
  | first batch | `tests/eval_cases_first_batch.json` | 15 |
  | second batch | `tests/eval_cases_second_batch.json` | 40 |
  | third batch | `tests/eval_cases_third_batch.json` | 17 |

  `scripts/evaluate_documents.py` šalje dokumente i pitanja kroz pravi API, uspoređuje odgovor s očekivanim izrazima i
  upisuje PASS / FAIL / REVIEW (ručna provjera) u `evaluation_results.json`. Skup koji se pokreće zadan je konstantom
  `CASES_PATH` na vrhu skripte (trenutno third batch).

### Rezultati evaluacije

| Skup | Pitanja | PASS | FAIL | REVIEW |
|---|---|---|---|---|
| first batch | 15 | 13 | 0 | 2 |
| second batch | 40 | 38 | 1 | 1 |
| third batch | 17 | 12 | 5 | 0 |

Ukupno 72 pitanja: 63 PASS, 6 FAIL, 3 REVIEW.

Što koji skup obuhvaća:
- **first batch:** 15 jednostavnih pitanja nad dva kratka jednostranična dokumenta (pravilnik za zaposlenike i izvješće tvrtke,
  oko 160-250 riječi), većinom doslovne činjenice, uz 2 pitanja na koja dokument izričito ne daje odgovor.
- **second batch:** 40 pitanja nad osam kratkih jednostraničnih dokumenata različitih vrsta (račun, potvrda, ugovor o najmu, NDA,
  tehnički list, zapisnik, bankovni izvod, izvješće o incidentu; oko 80-230 riječi), šest od njih s malom tablicom. Pitanja o
  brojevima, datumima i imenima, uz 1 pitanje bez odgovora u dokumentu.
- **third batch:** 17 pitanja nad dva dulja višestranična dokumenta (godišnje izvješće od 10 stranica i ugovor o uslugama od 11
  stranica, oko 1.700-2.100 riječi i 8 tablica ukupno). Činjenice su razasute po stranicama i tablicama, a 3 pitanja traže računanje
  ili zaključivanje. To je najteži skup.

**First batch (15 pitanja):** 13 prošlo, 0 palo, 2 za ručnu provjeru. Oba REVIEW pitanja (Q5 o imenu financijskog direktora, Q10 o imenu
izvršnog direktora) traže podatak koji dokument izričito ne navodi. Model nije javio da odgovora nema: u Q5 je vratio dugi nepovezani
odlomak o opremi i kontaktima, a u Q10 redak tablice `Fiscal year 2025: 120.`. Pri ručnoj provjeri oba su pogrešna.

**Second batch (40 pitanja):** 38 prošlo, 1 palo, 1 za ručnu provjeru.
- **FAIL (Q36, uzrok prekida rada):** odgovor je `internal gateway`, izvučen iz retka vremenske crte ("Root cause identified in the
  internal gateway"), umjesto iz rečenice o isteklom TLS certifikatu na internom API gatewayu. Pobijedio je kratki redak
  tablice, a točan odlomak je ostao neiskorišten.
- **REVIEW (Q7):** račun ne sadrži PDV identifikacijski broj dobavljača. Model ne prijavljuje da odgovora nema (vidi napomenu o QA
  modelu), pa je vratio IBAN. Pri ručnoj provjeri to je pogrešan odgovor. Isto kao u first batchu: sva tri pitanja bez odgovora u
  dokumentu (Q5 i Q10 u first batchu, Q7 u second batchu) dobila su pogrešan odgovor umjesto poruke da podatka nema.

**Third batch (17 pitanja):** 12 prošlo, 5 palo (70,6 %).
- 3 pitanja traže računanje ili zaključivanje (razlika prihoda, zbroj naknada, raspon u tablici razina) i ekstraktivni model ih ne
  može riješiti. Namjerno su ostavljena kao dokaz granice pristupa.
- 2 pitanja su stvarne greške dohvaćanja/odabira: tražena činjenica postoji u dokumentu, ali je pobijedio chunk s višom QA
  pouzdanošću (npr. redak tablice "Net profit: 138" umjesto rečenice o 72 % zaštićene proizvodnje).

## Ograničenja

- **OCR** čita samo engleski (`OCR_LANGUAGES` u `app/config.py`), traje nekoliko sekundi po stranici na CPU-u i najviše
  `MAX_OCR_PAGES` (20) stranica po PDF-u. Kvaliteta ovisi o skenu; rukopis i vrlo loši skenovi nisu pouzdani. EasyOCR
  spaja redove u odlomke, pa se tablice na slikama čitaju kao običan tekst (bez strukture redaka).
- Dokumenti i sesije žive u **memoriji** procesa: restart backenda ih briše.
- Nema autentikacije, ograničenja broja zahtjeva ni strukturiranog logiranja.
- Embeddingi se ne spremaju u cache; isti dokument uploadan dvaput gradi se dvaput.
- QA model je extractive: odgovor je dio teksta iz dokumenta, ne sažetak. Za pitanja koja traže sintezu više mjesta
  nije idealan. Kad odgovora nema, model ne javlja da ga nema (vidi napomenu o QA modelu), nego vraća najbolji pokušaj,
  zato je bitan prikaz izvora.
- Uspješan upload s djelomičnim neuspjehom vraća HTTP 200, a neuspjeli su u `errors`.
- Obrada dokumenta je sinkrona i CPU-intenzivna, pa velike datoteke blokiraju server.

## Kako je AI kod validiran

Dio koda razvijao sam uz AI asistenta (Claude Code). Kod nisam prihvaćao "naslijepo":

- **Pregled prije prihvaćanja.** Prvo sam pregledao što je generirano, tek onda dopuštao izmjene, i stalno pratio diff.
  Generiranje je išlo sekvencijalno, u malim koracima (faza po faza: upload i sesije, pitanja nad sesijom, UI, Docker,
  OCR), pa se svaka promjena mogla pratiti i razumjeti. Zato dobro poznajem većinu koda i prototip u cjelini.
- **Ručno testiranje na razini integracije.** Sam sam puštao PDF-ove i slike kroz sustav (kroz UI, Swagger i curl) i
  provjeravao što vraća, uključujući pogrešne ulaze (krivi tip datoteke, prazna datoteka, krivi sadržaj). Scenariji su
  kratki i jasni, pa se do ovog opsega moglo bez dodatnih logova.
- **Evaluacija.** Provjera kvalitete ubrzana je skriptom `evaluate_documents.py` i skupovima pitanja (first, second i
  third batch) s očekivanim odgovorima, umjesto ručnog ponavljanja pitanja.
- **Automatski testovi (pytest + CI)** čuvaju logiku API-ja (validacija, sesije, brisanje, odabir odgovora) od
  regresija pri svakoj izmjeni. Oni ne mjere kvalitetu odgovora; to rade evaluacijski skupovi.
- **Transparentnost odgovora.** Uz svaki odgovor vraća se izvorni chunk, pa se i sam rezultat modela može provjeriti.

## Demo

Snimke rada aplikacije nisu u repozitoriju zbog veličine, nego se preuzimaju preko linkova:

1. **Upload dokumenata i pitanja:** upload 5 dokumenata odjednom, zatim 3 pitanja nad sesijom. Uz svaki odgovor prikazan je izvor
   (datoteka, stranica i tekst chunka). Link za preuzimanje: *(link)*
2. **Upload slika (OCR):** isti tok, ali s uploadom slika koje čita EasyOCR. Link za preuzimanje: *(link)*

## Primjeri API zahtjeva

Primjeri pretpostavljaju backend na `http://127.0.0.1:8000` (lokalno ili kroz Docker).

### Upload više dokumenata (PDF i slike)

```bash
curl -X POST http://127.0.0.1:8000/upload \
  -F "files=@sample_docs/sample_employee_policy.pdf" \
  -F "files=@sample_docs/scanned_invoice_nordlicht.png"
```

Odgovor (skraćeno):

```json
{
  "session_id": "30c14c9f-...",
  "documents": [
    {"document_id": "...", "filename": "sample_employee_policy.pdf", "pages_processed": 1, "chunks_created": 2, "ocr_pages": 0},
    {"document_id": "...", "filename": "scanned_invoice_nordlicht.png", "pages_processed": 1, "chunks_created": 1, "ocr_pages": 1}
  ],
  "errors": [],
  "message": "Documents uploaded and indexed successfully."
}
```

`ocr_pages` je broj stranica pročitanih OCR-om. Za dodavanje u postojeću sesiju pošalji i `-F "session_id=30c14c9f-..."`.
Datoteke koje se ne mogu obraditi (nisu PDF/PNG/JPG ili sadržaj ne odgovara ekstenziji) nalaze se u `errors`, a ostale se
svejedno spremaju. Greška se vraća samo ako nijedna datoteka nije uspjela. Zbog kompatibilnosti odgovor još sadrži i stara
polja (`document_id`, `filename`, zbrojene `pages_processed` i `chunks_created`).

### Pitanje nad sesijom

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"session_id": "30c14c9f-...", "question": "What is the total amount due on the invoice?"}'
```

Odgovor (skraćeno; tekst chunka izostavljen):

```json
{
  "answer": "EUR 833.95",
  "source": {"document_id": "...", "filename": "scanned_invoice_nordlicht.png", "page": 1, "text": "..."},
  "retrieved_chunks": 3,
  "answer_method": "faiss_retrieval_and_qa",
  "debug_candidates": [ ... ]
}
```

`source.text` je chunk iz kojeg je odgovor izvučen. `debug_candidates` su svi razmatrani chunkovi s QA pouzdanošću
(za analizu i debugiranje).

### Pitanje nad jednim dokumentom

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"document_id": "...", "question": "What is the annual learning budget?"}'
```

Treba zadati **točno jedan** od `document_id` i `session_id`, inače je odgovor 400.

### Ostali endpointi

```bash
curl "http://127.0.0.1:8000/documents?session_id=30c14c9f-..."   # popis dokumenata (filter po sesiji je opcionalan)
curl -X DELETE http://127.0.0.1:8000/sessions/30c14c9f-...        # brisanje sesije i njezinih dokumenata
```

Kodovi grešaka: 400 neispravan zahtjev (prazno pitanje, krivi tip ili sadržaj datoteke, prazna datoteka, oba/nijedan ID),
404 nepoznat dokument ili sesija, 413 datoteka veća od 10 MB.
