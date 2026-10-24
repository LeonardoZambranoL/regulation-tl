# SPLADE + Dense mit optionalem Cross-Encoder

## Ziel und Reihenfolge

Zuerst möglichst viele relevante Quellen finden, danach die vorderen Kandidaten
ordnen, anschließend die tatsächliche Anwendbarkeit mit Quellenbelegen prüfen.
Ein Ähnlichkeitswert beweist weder eine Pflicht noch deren Nichtanwendbarkeit.

1. **Produkt und Datenstand festhalten.** Produktfakten von Annahmen trennen;
   Basis-/Änderungsfassung, Dokumenthash, Klausel-ID und PDF-Seiten erhalten.
   Der bestehende Index enthält ausschließlich Basisfassungen.
2. **Suchfragen bilden.** Aus der Spezifikation 12–20 kurze englische Facetten:
   Funktionen, Einbau, Werkstoffe, elektrische Eigenschaften, Prüfungen,
   Kennzeichnung, Dokumentation, Produktionskonformität, Definitionen und
   Ausnahmen. Unsichere Eigenschaften bleiben Suchhypothesen. Das ist für den
   englischen Korpus gedacht; deutsche Fragen benötigen eigene Validierung.
3. **Kandidaten unabhängig suchen.** Je Frage SPLADE und Dense auf exakt demselben
   zulässigen Korpus. Vorhandener Dense-Encoder: BGE small English v1.5;
   SPLADE: `prithivida/Splade_PP_en_v1`. Je Kanal ein konfigurierbarer Pool.
   Beide laufen lokal, einschließlich der Query-Encoder.
4. **Fusion.** Reciprocal Rank Fusion mit `k=60` und gleichem Kanalgewicht.
   Unterschiedliche Score-Skalen müssen dadurch nicht künstlich angeglichen werden.
   Das ist eine feste Baseline, kein gelerntes Optimum. Nicht in einem Kanal
   gefundene Kandidaten bleiben über den anderen erhalten. Beste Fenster pro
   Klausel werden dedupliziert, die Quellenmetadaten bleiben unverändert.
5. **Optionales Reranking.** Der lokale Cross-Encoder
   `Xenova/ms-marco-MiniLM-L-6-v2` ordnet nur die ersten 50/100/200 Kandidaten
   je Frage neu. Der Rest bleibt erhalten. Lange Query-/Passagetexte werden
   aufgeteilt und mit Max-Pooling ausgewertet, nicht still abgeschnitten.
   Der Encoder ist eine englische allgemeine Baseline, kein Fachgutachter.
6. **Fragen zusammenführen.** Round-robin über die Fragen, dann Klauseln
   deduplizieren. So dominiert nicht allein die Frage mit der längsten Trefferliste.
7. **Quellenkontext holen.** Ganze Seitenpakete samt Nachbarseiten, Tabellenbildern
   und aufgelösten Querverweisen verwenden. Definitionen und Ausnahmen gehören
   in die fachliche Prüfung. Nicht aufgelöste Verweise werden protokolliert.
8. **Claude prüft die Belege.** Der vorhandene Runner erstellt atomare Anforderungen,
   kontrolliert Zitate, Seiten/Fassungen, Bedingungen und Dopplungen. Unerledigte
   Kandidaten und Seiten bleiben sichtbar. Der Retriever darf sie nicht als
   fachlich ausgeschlossen deklarieren.
9. **Ausgabe einfrieren und getrennt bewerten.** Erst fertige Rankings speichern,
   anschließend Labels für die Evaluation laden/vergleichen. Die bekannten
   Seitenlabels werden nie an Query-Planer oder Retriever übergeben.

## Warum der Cross-Encoder optional bleibt

Für regulatorische Vollständigkeit zählt Recall, nicht nur die Präzision der
allerersten Treffer. Ein allgemeiner Reranker kann semantisch ähnliche konkrete
Lichtanforderungen bevorzugen und seltene Dokumentations-/Prüfpflichten nach hinten
schieben. Deshalb entscheiden gleiche Seitenbudgets und die Messwerte, ob das
Reranking aktiviert wird. Niedrige Scores führen zu keiner fachlichen Ablehnung.
Auch eine größere Kandidatenvereinigung hilft nur, wenn nachgelagerte Seiten- und
Tokenbudgets die zusätzlichen Quellen tatsächlich berücksichtigen.

## Reproduzieren und Wiederaufnahme

Die Installations-, Daten- und Ausführungsbefehle für diesen eigenständigen
Repository-Snapshot stehen in [README.md](README.md). Der Einstieg ist
`src/regulation-db/workflows/run_splade.py`; `finish_review.py` kann geprüfte
Extraktionen und gültige Review-Entscheidungen aus einem angehaltenen Lauf
übernehmen. Wiederholter Quellenkontext wird dabei verlustfrei referenziert.

Die API-Grenze gilt für das gemeinsame Ledger unter `runs/.api`, einschließlich
bereits verbuchter Läufe. Der vollständige Runner sendet Originalseiten und
Produktbilder an Anthropic; der lokale Retrieval-Benchmark tut das nicht.
Retrieval und Indexaufbau laufen lokal. Ein Oracle-Server ist dafür nicht nötig.
Modell-Dateihashes und Korpusfingerprint werden gespeichert. Nur ein Indexaufbau
pro Indexverzeichnis darf gleichzeitig laufen.

## Aussagekraft des Vergleichs

`benchmark_splade.py` prüft BM25, Dense, bisherige Fusionen, SPLADE allein,
SPLADE+Dense-RRF mit Pools 100/300/1000 und Reranking-Köpfe 50/100/200.
Alle Varianten laufen über dieselben Fragen und Seitenbudgets 20/50/100/200.
Zusätzlich wird die Seitenabdeckung der gesamten Kandidatenvereinigung gemessen.

Die Varianten sind Entwicklungsdiagnostik für **einen** Produktfall. Seiten-Recall
ist keine semantische Anforderungsgenauigkeit. Ganze Klauselseitenbereiche können
Relevanz zu großzügig gutschreiben. Die Reranking-Varianten verwenden gemeinsam
berechnete CE200-Scores; ihre ausgewiesenen CE-Zeiten sind deshalb keine separaten
Laufzeitmessungen. Mehr Facetten kosten mehr Encoder-/Suchaufrufe.

Für eine belastbare nächste Iteration: weitere unabhängig gelabelte Produkte,
Gruppentrennung nach Produktfamilie, fachliche Beurteilung neuer Treffer und
fehlender Pflichten; anschließend Recall/nDCG, End-to-End-Qualität, Latenz und
Tokenkosten gemeinsam vergleichen. Keine Optimierung auf den späteren Testsatz.
