# Zwei Abläufe ohne Training

Aktuelle Entscheidung vom 24.10.2026: Aus Kostengründen wird nur der gezielte
Ablauf mit 32 Seitenpaketen abgeschlossen. Der gründliche Lauf wurde nach einem
Teil der Quellenprüfung gestoppt und ist kein fertiger Vergleichsmaßstab.
Die Kostenobergrenze dieses Workflows einschließlich seiner Vorversuche beträgt
12 US-Dollar. Parallel laufende andere Tests werden separat abgerechnet.
Der aktuelle Versuch liegt unter `runs/dev-budget32-offline`; das Ergebnis ist eingefroren und mit dem offiziellen
Quellenbenchmark gemessen: 25,79 % Seiten-F2, 32,50 % Präzision und 24,53 %
Trefferabdeckung (13 von 53 Referenzseiten). 233 Anforderungen sind enthalten.
73 weitere Entwürfe bleiben ohne Schlussprüfung und sind ausgeschlossen.
Die Kosten dieses Workflows einschließlich Vorversuchen betragen 11,909740 Dollar.
Devanshs bester gespeicherter Ansatz erreicht mit demselben Prüfer 84,42 %
Seiten-F2. Die Bedingung für zusätzliches Budget ist damit nicht erfüllt.
Wenn die Kostenbremse während der Schlussprüfung greift, bleiben noch nicht geprüfte
Entwürfe offen und werden nicht in die Abgabe übernommen. Das ist ein ausdrücklich
unvollständiges Ergebnis, keine erfolgreich abgeschlossene Gesamtprüfung.

Wir bauen aus einer Produktbeschreibung eine Liste belegbarer Anforderungen.
Die einzige vorhandene Musterlösung wird ausschließlich nach dem Einfrieren
der Ausgaben durch einen getrennten Benchmark gelesen. Der Solver liest weder sie noch alte
Einreichungen oder Scores. Die bekannte Rückleuchte bleibt trotzdem ein
Entwicklungsfall, kein unabhängiger Nachweis für neue Produkte.

## Übersicht in einfacher Sprache

| Schritt | Gründlich | Gezielt |
|---|---|---|
| Produkt verstehen | Beschreibung und Produktbild lesen; Fakten und offene Fragen notieren | Gleich |
| Vorschriften wählen | Alle gelieferten Basisvorschriften anhand ihrer Titel und Eingangsseiten prüfen | Gleich |
| Quellen prüfen | Alle Seiten der gewählten Vorschriften durcharbeiten | Mit BM25 und Dense suchen, aufgelösten Verweisen folgen und eine begrenzte Zahl von Seitenpaketen prüfen |
| Tabellen lesen | Originalbilder der geprüften PDF-Seiten zusätzlich zum Text lesen | Gleich |
| Anforderungen schreiben | Eine Pflicht pro Eintrag, mit Bedingungen, Grenzen und Quellenbeleg | Gleich |
| Schlussprüfung | Anwendbarkeit, Beleg und mögliche Doppelungen prüfen | Gleich |
| Offene Stellen | Unklarheiten und fehlende Belege bleiben sichtbar | Zusätzlich bleiben nicht ausgewählte Seiten/Kandidaten ausdrücklich ungeprüft |

Kein Training, kein lernendes Mischgewicht und keine automatische Abgabe.
Die gezielte Suche vereinigt BM25- und Dense-Treffer und verfolgt aufgelöste
Querverweise. Sie nutzt keine aus Goldantworten gewonnenen Regulationslisten.

„Gründlich“ bedeutet eine vollständige Durchsicht der **ausgewählten** Vorschriften.
Eine falsche Ausschlussentscheidung bei der Vorschriftenwahl kann weiterhin Lücken
erzeugen. Die Auswahl liest die ersten drei Seiten je Dokument. Unsicherheit wird
beibehalten und mitgeprüft. Das ist ein allgemeiner Startpunkt, keine Garantie.

## Was technisch fertig ist

- Gemeinsame, fallunabhängige Prompts; ein Modell für beide Varianten.
- Angeheftete Originalseiten für PDF-Tabellen und Abbildungen.
- Übergeordnete Kapitelbedingungen werden auch aus weiter entfernten Seiten mitgegeben;
  die Schlussprüfung erhält diese Bedingungen ebenfalls. So darf etwa eine Vorschrift
  nur für einen besonderen Betriebszustand nicht als allgemeine Pflicht erscheinen.
- Prüfung, dass Zitate auf den angegebenen Textseiten vorkommen; Bildbelege
  erfordern eine tatsächlich mitgesendete Seitenabbildung.
- Jede im geprüften Paket enthaltene maschinelle Kandidatenstelle braucht eine Entscheidung.
- Fehlende/ungeprüfte Stellen werden niemals automatisch ausgeschlossen.
- Zwischenspeicher für API-Antworten und Fortsetzen unterbrochener Läufe.
- Gemeinsames API-Kostenbuch; `resume_budgeted.py` ordnet neue Kosten unter einer
  exklusiven Sperre diesem Workflow zu und hält dessen eigene Gesamtgrenze ein.
- Offizieller Schema-Validator, Basisversions-/Seitenprüfung und unveränderliche Ausgabe-Hashes.
- Getrennte lokale Auswertung und manuelles Scorebuch für den Wettbewerb.

Struktur- und Zitatprüfungen beweisen nicht, dass jede fachliche Interpretation
richtig ist. Die Schlussprüfung findet Doppelungen innerhalb kleiner Gruppen,
nicht garantiert zwischen allen Gruppen. Nicht aufgelöste Querverweise und
fehlende Quellen werden protokolliert; der Solver erfindet deren Inhalt nicht.
Die vorliegende Version bearbeitet solche offenen Quellenfragen noch nicht in
einer zusätzlichen autonomen Recherche-Runde.

## Heute: Rückleuchte prüfen

Alle Befehle aus dem Workspace-Stamm. Die Umgebung aus dem Retrieval-Modul wird
mitbenutzt; Zusatzpakete stehen in `requirements.txt`.

```sh
PY=regulation-db/retrieval/.venv/bin/python
$PY -m pip install -r regulation-db/workflows/requirements.txt
$PY regulation-db/workflows/run.py prepare \
  --case-dir industrial-ai-hackathon/cases/dev-rear-lamp \
  --out regulation-db/workflows/runs/dev-v1 --team-id development
```

Den API-Key als `ANTHROPIC_API_KEY` in der lokalen Umgebung oder in einer
geschützten Datei **außerhalb des Repositories** bereitstellen. Den Schlüssel
nicht in den Chat, in Befehlsargumente oder in die Versionsverwaltung schreiben.
`--key-file` nimmt nur den Pfad, niemals den Schlüssel selbst.

```sh
$PY regulation-db/workflows/run.py run \
  --out regulation-db/workflows/runs/dev-v1 --flow both \
  --budget-usd 10 --key-file /PFAD/ZUR/GESCHUETZTEN/DATEI
```

Optional zuerst `--max-packets 1` für einen Pilotlauf. Er führt Produktverständnis,
Vorschriftenwahl und ein Quellenpaket aus, erzeugt aber keine scheinbar vollständige
Einreichung. Danach denselben Befehl ohne `--max-packets` starten.

Der API-Lauf überträgt Produktspezifikation, Produktbild und gewählte Quelltexte/
PDF-Seitenbilder an Anthropic. Die Musterlösung ist nicht Bestandteil der Anfragen.
Für diese Übertragung muss der Nutzer autorisiert sein und zugestimmt haben.

```sh
$PY regulation-db/workflows/evaluate.py \
  --experiment regulation-db/workflows/runs/dev-v1 \
  --expected industrial-ai-hackathon/cases/dev-rear-lamp/expected.json \
  --out regulation-db/workflows/runs/dev-v1/comparison.json
```

Diese Auswertung benötigt abgeschlossene, eingefrorene Ausgaben beider Varianten.
Sie misst die offiziellen lokalen Regulations-/Seitenmetriken. Der semantische
Anforderungsscore kommt erst von der Wettbewerbsplattform. Eine reine Zahl
ausgegebener Anforderungen ist kein Qualitätsmaß.

## Morgen: neuer Fall

1. Den bereitgestellten neuen Fall und gegebenenfalls neue Vorschriften laden.
2. Prüfen, ob die Quelldatenbank zum neuen Regulationsindex passt. `prepare` stoppt
   bei Abweichungen; dann zuerst den Korpus und bei Bedarf den Retrieval-Index
   neu bauen. Neue Produktfragen allein benötigen kein neues Dokument-Embedding.
3. Den neuen Fall mit neuer Ausgabe-ID vorbereiten. Den echten Teamnamen angeben.
4. Den gründlichen Ablauf starten; parallel dazu manuell offene Produktannahmen
   prüfen. Der Runner selbst führt beide Varianten nacheinander aus.
5. Die gültige, geprüfte Ausgabe auf der Plattform einreichen und ihren Score
   zum unveränderten Datei-Hash notieren.
6. Den gezielten Ablauf vergleichen. Weitere Varianten immer in einem neuen
   Experimentordner mit dokumentierter Änderung erstellen.

```sh
$PY regulation-db/workflows/run.py prepare \
  --case-dir industrial-ai-hackathon/cases/NEUER_FALL \
  --out regulation-db/workflows/runs/neu-v1 --team-id EURE_TEAM_ID
$PY regulation-db/workflows/run.py run \
  --out regulation-db/workflows/runs/neu-v1 --flow both --budget-usd 10
```

`--budget-usd` ist die gemeinsame Obergrenze des API-Ledgers unter `runs/.api`,
einschließlich früherer dort verbuchter Experimente. Für eine neue autorisierte
Gesamtsumme entsprechend erhöhen; alte Ausgaben nicht löschen, um die Grenze
zu umgehen. Preisannahmen und Modellkennung sind im Code festgehalten.

## Vier Stunden sinnvoll nutzen

Die Zeitfenster sind ein Plan, keine gemessene Laufzeitgarantie:

- **Erste 15 Minuten:** Eingaben, Basisversionen und Produktannahmen prüfen; Lauf starten.
- **Bis etwa Minute 90:** Erste belastbare Ausgabe erstellen, offene Quellenfragen
  prüfen und einen ersten Plattformscore sichern. Wenn der Lauf länger dauert,
  keine unvollständige Ausgabe als vollständig behandeln.
- **Minute 90–180:** Wenige begründete Varianten testen, jeweils nur einen Faktor
  ändern: etwa mehr Quellenabdeckung, Umgang mit bedingten Pflichten oder
  strengere Prüfung auf Doppelungen. Ein einzelner Score sagt nicht, welche konkrete
  Anforderung falsch ist; deshalb immer auch die tatsächlichen Änderungen prüfen.
- **Letzte 30–60 Minuten:** Änderungen beenden, gewählten Stand prüfen, final
  einreichen und die Plattformbestätigung kontrollieren. Genügend Reserve lassen.

Laut mitgelieferter Challenge-Anleitung zählt beim neuen Fall die **letzte gültige
Einreichung**. Die dort genannte Uploadgrenze ist fünf pro Stunde; morgen auf der
Plattform prüfen, ob diese Regeln unverändert gelten. Dieses Werkzeug lädt nichts hoch.

```sh
$PY regulation-db/workflows/scoreboard.py \
  --ledger regulation-db/workflows/runs/platform-scores.json \
  --run regulation-db/workflows/runs/neu-v1/thorough \
  --score TATSAECHLICHER_SCORE --note 'Erster gründlicher Lauf'
```

Das Scorebuch zeigt den besten **eingetragenen** Stand derselben Aufgabe und
Metrik; es weiß nicht selbst, was aktuell auf der Plattform eingereicht ist.

## Ergebnisse, Kosten und Wiederaufnahme

Unter jedem Experiment liegen `manifest.json`, `profile.json`, `scope.json`,
Quellenpläne, Originalseitenbilder und Paketantworten. Die beiden Unterordner
`thorough` und `targeted` enthalten nach Abschluss `submission.json`, `freeze.json`,
`report.json`, `coverage.jsonl`, Belege und Schlussprüfungen.

`coverage_complete=false` ist ein Hinweis auf offene Abdeckung, keine versteckte
Behauptung von Vollständigkeit. Der gezielte Ablauf wird wegen seiner ungeprüften
Stellen gewöhnlich keine vollständige Abdeckung melden.

Unveränderte API-Anfragen werden aus `runs/.api/responses` wiederverwendet.
Die gezielte Variante darf deshalb bereits bezahlte, identische Paketprüfungen
nutzen. Für den Vergleich wird zusätzlich der geschätzte Modellpreis eines
eigenständigen Durchlaufs ausgewiesen; ein Cache-Treffer wird nicht als kostenloser
eigenständiger Lauf verkauft.

Vor jeder Generierung wird ein konservativer Betrag für Eingabe plus maximale
Ausgabe reserviert. Bei einem Netzwerkabbruch mit unklarem Ausgang bleibt die
Reservierung bestehen. Es erfolgt keine blinde Wiederholung mit möglicher
Doppelabrechnung. `status.json` und `runs/.api/api-ledger.json` erklären den Stopp.
Die Grenze berücksichtigt dokumentierte Standard-Tokenpreise, nicht eventuelle
Steuern oder abweichende Vertragskonditionen.

Quellen für die API-Implementierung, geprüft am 24.10.2026:
[Messages API](https://platform.claude.com/docs/en/api/messages/create),
[JSON-Ausgaben](https://platform.claude.com/docs/en/build-with-claude/structured-outputs),
[Tokenzählung](https://platform.claude.com/docs/en/api/messages/count_tokens),
[Preise](https://claude.com/pricing).

```sh
$PY -m unittest discover -s regulation-db/workflows -p 'test_*.py' -v
```
