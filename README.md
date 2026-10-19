# Document Insight Service

REST API (FastAPI) koji prima PDF dokumente, izvlači tekst i tablice, i odgovara na pitanja o njihovom sadržaju
pomoću RAG pristupa: semantičko pretraživanje (FAISS) + model za question answering (RoBERTa SQuAD2).
Uz API dolazi i Streamlit UI.

> **Status projekta:** PDF obrada, RAG, sesije s više dokumenata i UI su gotovi.
> Još nije napravljeno: podrška za slike/OCR, cache embeddinga. Vidi [Ograničenja i plan](#ograničenja-i-plan).

## Što servis radi

1. `POST /upload`: prima jedan ili više PDF-ova, izvlači tekst i tablice, dijeli ih u chunkove i gradi FAISS indeks.
   Dokumenti se grupiraju u **sesiju**.
2. `POST /ask`: prima pitanje i pretražuje jedan dokument ili sve dokumente sesije, vraća odgovor, izvor
   (ime datoteke, stranica, tekst) i detalje dohvaćanja.
3. `DELETE /sessions/{id}`: briše sesiju i njezine dokumente iz memorije.

## Tehnologije i zašto

| Dio | Alat | Zašto |
|---|---|---|
| API | **FastAPI** | Brz razvoj, validacija zahtjeva (Pydantic), automatska dokumentacija na `/docs`. |
| Ekstrakcija teksta | **PyMuPDF** | Brza i točna za PDF-ove s tekstualnim slojem; ima detekciju tablica, pa se retci tablica mogu tretirati posebno. |
| Embeddingi | **sentence-transformers `all-MiniLM-L6-v2`** | Mali model (brz na CPU-u) s dobrom semantičkom kvalitetom za pretragu. |
| Vektorska pretraga | **FAISS** (`IndexFlatIP`) | Egzaktna pretraga po kosinusnoj sličnosti (normalizirani vektori); za ovu veličinu dokumenata je dovoljno brza i bez dodatne infrastrukture. |
| QA model | **`deepset/roberta-base-squad2`** (Hugging Face Transformers) | Extractive QA: vraća dio teksta iz dokumenta, pa je odgovor provjerljiv i ne "halucinira". SQuAD2 model zna prepoznati da odgovora nema. Radi lokalno, bez API ključa. |
| UI | **Streamlit** | Najbrži način da se tok upload → pitanje → izvor pokaže u pregledniku. |
| Testovi | **pytest** + FastAPI `TestClient` | Brzi API testovi bez pokretanja servera. |
| CI | **GitHub Actions** | Pokreće pytest na svaki push i pull request. |

### Kako to radi (RAG tok)

```
PDF → PyMuPDF (tekst + tablice) → chunkovi (180 riječi, preklapanje 35)
    → MiniLM embeddingi → FAISS indeks (po dokumentu)

Pitanje → embedding → FAISS top-5 chunkova po dokumentu
        → RoBERTa QA nad svakim chunkom → odgovor s najvećom pouzdanošću
```

- **Tablice** se pretvaraju u tekst "jedna rečenica po retku" i indeksiraju kao zasebni chunkovi. U trenutku pitanja
  QA modelu se daje samo redak tablice koji je najsličniji pitanju (`select_best_row`).
- **Sesija:** kod pitanja nad sesijom dohvat se radi zasebno u svakom dokumentu, svi kandidati idu u isti QA krug i
  pobjeđuje onaj s najvećom QA pouzdanošću (sličnost dohvaćanja je dodatni kriterij kod izjednačenja).
- Modeli se učitavaju **lijeno**, pri prvom pitanju ili uploadu, pa prvi zahtjev traje duže.

## Struktura projekta

```
app/
  main.py           API rute (/upload, /ask, /documents, /sessions)
  schemas.py        Pydantic modeli zahtjeva
  state.py          spremanje dokumenata i sesija u memoriji
  config.py         konstante (limiti, veličina chunka, top-k)
  pdf_processor.py  ekstrakcija teksta i tablica (PyMuPDF)
  chunking.py       dijeljenje u chunkove
  retrieval.py      embeddingi, FAISS, odabir retka tablice
  models.py, qa.py  lijeno učitavanje modela
frontend/streamlit_app.py   Streamlit UI
sample_docs/                12 testnih PDF-ova
tests/                      pytest testovi i skupovi pitanja za evaluaciju
scripts/evaluate_documents.py   evaluacija kvalitete odgovora
.github/workflows/test.yaml     CI
```

## Pokretanje (ručna instalacija)

Potreban je Python 3.13 (isti kao u CI-ju). Iz mape projekta:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-ui.txt
```

(Linux/macOS: `source .venv/bin/activate`, pa `pip install -r requirements-dev.txt -r requirements-ui.txt`.)

Prvo pokretanje skida modele s Hugging Facea (par stotina MB) pa treba internet.

### Backend

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

API je na http://127.0.0.1:8000, a interaktivna dokumentacija na http://127.0.0.1:8000/docs.

### Frontend (Streamlit)

U drugom terminalu, dok backend radi:

```powershell
.venv\Scripts\streamlit.exe run frontend/streamlit_app.py
```

UI je na http://localhost:8501. URL backenda može se promijeniti u sidebaru.

U UI-ju možeš odabrati više PDF-ova odjednom, postavljati pitanja nad cijelom sesijom ili jednim dokumentom,
vidjeti izvor odgovora (datoteka i stranica) te obrisati sesiju.

> **Napomena o Swagger UI-ju:** polje `files` u `/docs` prikazuje se kao `array<string>` i ne nudi odabir datoteka
> (ograničenje Swaggera s OpenAPI 3.1). Za više datoteka koristi curl, Python ili Streamlit UI.

### Docker

Potreban je samo Docker Desktop (Python i biblioteke nisu potrebni). Iz mape projekta:

```bash
docker compose up --build
```

- API: http://localhost:8000/docs
- UI: http://localhost:8501

Prvi build traje nekoliko minuta jer instalira CPU verziju torch-a i ugrađuje Hugging Face modele u image
(zato prvi `/ask` nije spor i kontejner radi bez interneta). Sljedeći buildovi koriste cache slojeva, pa promjena koda
traje sekunde. Nakon `git pull` uvijek pokreni s `--build`, inače se koristi stari image.

Razvoj bez ponovnog builda (kod se montira u kontejner, uvicorn radi s `--reload`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Zavisnosti su podijeljene: `requirements.txt` (backend), `requirements-ui.txt` (Streamlit), `requirements-dev.txt` (backend + testovi).
Za ručnu instalaciju s testovima koristi `pip install -r requirements-dev.txt` i `pip install -r requirements-ui.txt`.

## Primjeri API zahtjeva

### Upload više PDF-ova

```bash
curl -X POST http://127.0.0.1:8000/upload \
  -F "files=@sample_docs/incident_report_payment_api.pdf" \
  -F "files=@sample_docs/sample_employee_policy.pdf"
```

Odgovor (skraćeno, vrijednosti su ilustrativne):

```json
{
  "session_id": "3f6c...",
  "documents": [
    {"document_id": "a1...", "filename": "incident_report_payment_api.pdf", "pages_processed": 2, "chunks_created": 4},
    {"document_id": "b2...", "filename": "sample_employee_policy.pdf", "pages_processed": 3, "chunks_created": 6}
  ],
  "errors": [],
  "message": "Documents uploaded and indexed successfully."
}
```

Za dodavanje u postojeću sesiju pošalji i `-F "session_id=3f6c..."`. Datoteke koje se ne mogu obraditi (npr. nisu PDF)
nalaze se u `errors`, a ostale se svejedno spremaju. Greška se vraća samo ako nijedna datoteka nije uspjela.

Zbog kompatibilnosti odgovor još sadrži i stara polja (`document_id`, `filename`, zbrojene `pages_processed` i `chunks_created`).

### Pitanje nad sesijom

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"session_id": "3f6c...", "question": "What is the annual learning budget?"}'
```

### Pitanje nad jednim dokumentom

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"document_id": "b2...", "question": "What is the annual learning budget?"}'
```

Treba zadati **točno jedan** od `document_id` i `session_id`, inače je odgovor 400.

Odgovor (oblik; vrijednosti ilustrativne):

```json
{
  "answer": "...",
  "source": {"document_id": "b2...", "filename": "sample_employee_policy.pdf", "page": 2, "text": "..."},
  "retrieved_chunks": 10,
  "answer_method": "faiss_retrieval_and_qa",
  "debug_candidates": [ ... ]
}
```

### Ostali endpointi

```bash
curl "http://127.0.0.1:8000/documents?session_id=3f6c..."   # popis dokumenata (filter po sesiji je opcionalan)
curl -X DELETE http://127.0.0.1:8000/sessions/3f6c...        # brisanje sesije i njezinih dokumenata
```

Kodovi grešaka: 400 neispravan zahtjev (prazno pitanje, krivi tip datoteke, prazna datoteka, oba/nijedan ID),
404 nepoznat dokument ili sesija, 413 datoteka veća od 10 MB.

## Testovi i evaluacija

```powershell
.venv\Scripts\python.exe -m pytest -v                       # unit/API testovi, brzi, bez pravih modela
.venv\Scripts\python.exe scripts/evaluate_documents.py      # evaluacija kvalitete s pravim modelima, sporije
```

- **pytest** provjerava ispravnost koda (validacija, sesije, brisanje, odabir odgovora). CI ga pokreće na svaki push.
- **evaluate_documents.py** postavlja pitanja nad `sample_docs/` s pravim modelima i uspoređuje odgovore s očekivanim
  (`tests/eval_cases_third_batch.json`). Rezultat upisuje u `evaluation_results.json`. Zadnji spremljeni rezultat: 12 od 17
  prošlo automatski, 5 palo (stariji od zadnjih izmjena; treba ga ponovno pokrenuti).

## Ograničenja i plan

- Podržani su samo PDF-ovi s tekstualnim slojem. **Slike i skenirani PDF-ovi (OCR) još nisu podržani**; planiran je EasyOCR.
- Dokumenti i sesije žive u **memoriji** procesa: restart backenda ih briše.
- Nema autentikacije ni ograničenja broja zahtjeva; nema strukturiranog logiranja.
- Embeddingi se ne spremaju u cache; isti PDF uploadan dvaput gradi se dvaput.
- QA model je extractive: odgovor je dio teksta iz dokumenta, ne sažetak. Za pitanja koja traže sintezu više mjesta
  nije idealan.
- Uspješan upload s djelomičnim neuspjehom vraća HTTP 200, a neuspjeli su u `errors`.
- Obrada PDF-a je sinkrona i CPU-intenzivna, pa velike datoteke blokiraju server.

## Kako je AI kod validiran

*(dopuniti prije predaje: npr. pytest testovi, evaluacijski skup, ručno testiranje kroz UI i curl)*
