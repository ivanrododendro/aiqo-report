.. _report_templates:

Struttura dei Template HTML
===========================

Il report HTML è generato a partire da un insieme di template *Jinja2* collocati in
``src/aiqo_pg_ai_report/report_templates/``.

Il file principale è ``report_template.html`` che funge da entry point
e include le varie sezioni strutturali (head, dati globali, contenuto principale e script).

Diagramma della Struttura dei Template
--------------------------------------

Il diagramma seguente mostra le relazioni di inclusione tra i file HTML principali.

.. mermaid::

    graph TD
        A[report_template.html] --> B[_head.html]
        A --> C[_global_data.html]
        A --> D[_main_content.html]
        A --> E[_scripts.html]

        D --> F[components/_global_synthesis.html]
        D --> G[components/_daily_tabs.html]
        D --> H[components/_context_section.html]
        G --> I[components/_query_accordion.html]
        D --> J[_macros.html]

Descrizione
-----------

- **report_template.html**: punto di ingresso, definisce la struttura di base della pagina HTML.
- **_head.html**: contiene il titolo, i meta-tag e i riferimenti a fogli di stile.
- **_global_data.html**: espone i dati globali del report.
- **_main_content.html**: struttura e incorpora le sezioni principali.
- **_scripts.html**: include gli script JavaScript e l’inizializzazione delle funzionalità dinamiche.
- **components/\***: moduli riutilizzabili che formano il corpo del report (come sintesi globale,
  schede giornaliere e accordion delle query).
- **_macros.html**: contiene macro Jinja2 per funzioni comuni nei template.

---

Con Sphinx configurato (aggiungendo `sphinxcontrib.mermaid` in `extensions` del file `conf.py`),
il diagramma viene renderizzato automaticamente nella documentazione HTML.
