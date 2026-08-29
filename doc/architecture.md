# Data Migration Studio - Technical Architecture & Core Principles

This document explains the internal mechanisms, transaction management, data integrity guarantees, and sequence workflows of **Data Migration Tools Studio**.

---

## 1. 6-Stage Pipeline Execution Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as Migration Engineer
    participant Console as OWL 3 Live Console
    participant Plan as migration.plan
    participant Step as migration.plan.step
    participant Job as migration.job
    participant Ext as migration.extraction
    participant Conn as migration.connection
    participant Transform as migration.mapping.transform
    participant Val as migration.validation.rule
    participant DB as PostgreSQL / Odoo ORM
    participant Log as migration.log
    participant Map as migration.record.map

    User->>Plan: Execute Plan (Live / Dry-Run)
    Plan->>Console: Initialize Live State Stream
    loop For each Stage & Step
        Plan->>Step: _execute_step()
        Step->>Job: _execute_job()
        alt Extraction Query Configured
            Job->>Ext: execute_extraction(limit)
            Ext->>Ext: _validate_query_safety() + Bind :watermark
            Ext->>Conn: _fetch_raw_records()
            Conn-->>Ext: Raw Rows + Columns
            Ext-->>Job: Return Transformed Extraction Batch
        else Default Connection Query
            Job->>Conn: _fetch_raw_records()
            Conn-->>Job: Return Raw Rows + Column Metadata
        end

        loop For each Row (1 to N)
            Job->>DB: Open Savepoint (cr.savepoint())
            Job->>Transform: Apply Field Transformation Pipelines
            Transform-->>Job: Transformed Field Values Dictionary
            Job->>Val: Evaluate Pre-Load Validation Rules
            alt Validation Failed (Action = reject_record)
                Val-->>Job: Reject Record
                Job->>Log: Log Rejection Warning / Error
                Job->>DB: Rollback Savepoint (Skip Row)
            else Validation Passed
                Job->>Map: Check Existing Map / Composite Key
                alt Record Exists (Checksum Unchanged)
                    Job->>Log: Log Skipped (Unchanged)
                else Record Exists (Checksum Changed)
                    Job->>DB: target_model.write(vals)
                    Job->>Map: Update Checksum & Timestamp
                    Job->>Log: Log Updated
                else New Record
                    Job->>DB: target_model.create(vals)
                    Job->>DB: Register ir.model.data (XML ID)
                    Job->>Map: Create Cross-Reference Entry
                    Job->>Log: Log Created
                end
                Job->>Val: Evaluate Post-Load Verification Rules
                Job->>DB: Release Savepoint (Commit Row)
            end
        end

        alt Dry-Run Simulation Mode
            Job->>DB: Rollback Entire Step Savepoint
        end
        Job-->>Step: Update Step Metrics (Total, Success, Errors, Speed)
        Step-->>Plan: Step State (Done / Failed)
    end
    Plan-->>Console: Final Plan Execution Summary
```

---

## 2. Visual Extraction & Query Studio Architecture

The **Extraction Studio** operates as a smart intermediary layer between the raw source data connection and downstream mapping templates:

```mermaid
flowchart LR
    subgraph Discovery["1. Schema Discovery"]
        CONN["migration.connection"] -->|"inspect_source_schema()"| SCH["Tables, Columns & Types"]
    end

    subgraph Studio["2. Visual Extraction Studio (OWL 3)"]
        SCH --> V1["Table Explorer"]
        SCH --> V2["Column Selector & Aliasing"]
        V2 --> V3["WHERE Filter Builder"]
        V3 --> V4["ORDER BY Sorting"]
        AI["AI Extraction Assistants"] -->|"NL Query Generation"| V2
        AI -->|"Performance & Index Advisor"| V3
        AI -->|"Watermark Advisor"| WM["Watermark State"]
    end

    subgraph Compilation["3. Query Compilation & Safety"]
        V2 & V3 & V4 --> COMP["compile_query_from_visual()"]
        COMP --> SAFE["_validate_query_safety()"]
        SAFE -->|"Blocks DROP/DELETE/UPDATE"| EXE["execute_extraction()"]
    end

    subgraph Downstream["4. Downstream Synchronization"]
        V2 -->|"get_extraction_columns()"| TMPL["migration.template"]
        EXE -->|"Sample Records (Limit N)"| PREV["Live Sandbox Table"]
    end
```

### Key Technical Properties:
1. **Multi-Dialect Catalog Introspection**:
   - `inspect_source_schema()` queries the system catalog (`information_schema.tables`, `information_schema.columns` for Postgres/MySQL, `sqlite_master` / `PRAGMA table_info` for SQLite) or inspects file headers to provide structured table/view and column schemas to the UI.
2. **Deterministic SQL Compiler**:
   - Compiles selected field projections, aliases (`col AS alias`), type casts (`CAST(col AS type)`), WHERE clauses, and sorting into standard ANSI SQL.
3. **Strict Server-Side Read-Only Guard**:
   - Before any query is executed against the source database, `_validate_query_safety()` checks for forbidden DDL/DML keywords (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `TRUNCATE`, `ALTER`, `CREATE`, `GRANT`, `REVOKE`, `EXEC`, `SHUTDOWN`).
4. **Dynamic Downstream Field Projection**:
   - When a `migration.template` is linked to an extraction query, `get_available_source_variables()` uses `extraction_id.get_extraction_columns()`, ensuring that any aliases defined in the extraction query are immediately available for transformation pipelines and target field mapping.

---

## 3. Zero-Failure Savepoint Isolation

One of the biggest pain points in enterprise data migration is when a single malformed row in a 50,000-row file crashes the entire transaction, rolling back thousands of previously processed records.

### How Data Migration Studio Solves This:
- Every record execution is encapsulated inside an isolated PostgreSQL savepoint:
  ```python
  with self.env.cr.savepoint():
      # All transformations, lookups, and ORM create/write calls happen here
  ```
- If an uncaught constraint error occurs (e.g. unique constraint violation, foreign key failure, invalid date format), the database rolls back **only the changes made for that specific row**.
- The execution engine catches the exception, logs the complete traceback alongside the raw and transformed JSON payloads in `migration.log`, and immediately proceeds to row $N+1$.
- Batch progress commits occur periodically (every 100 records) to keep database locks minimal and memory footprints predictable.

---

## 4. MD5 Checksum Change Detection

To support efficient incremental migrations and recurring synchronizations, the module uses MD5 checksumming:

$$\text{Checksum} = \text{MD5}\left(\text{json.dumps}(row\_data, \text{sort\_keys}=\text{True})\right)$$

1. When a source record is processed, its MD5 hash is stored in `migration.record.map`.
2. On subsequent runs:
   - If the source record exists in Odoo and its MD5 checksum is identical, the ORM `write()` operation is skipped completely.
   - This reduces database write I/O by over **90%** on recurring synchronization jobs.

---

## 5. Incremental Watermark Delta Extraction

For high-volume SQL databases and API integrations, full table scans are inefficient.

1. The `migration.extraction` model records `last_watermark_value` (e.g. timestamp `'2026-08-27 10:00:00'` or sequential ID `150293`).
2. When executing the extraction query:
   - The query binds `:watermark` -> `WHERE updated_at > :watermark`.
   - The extractor tracks the maximum watermark value across all extracted rows.
3. For non-SQL sources (CSV, Excel, REST APIs), the engine performs high-performance in-memory delta comparison based on `watermark_datatype` (`datetime`, `date`, `integer`).
4. Upon successful job completion, `last_watermark_value` is updated atomically.

---

## 6. Relational Resolution Strategy Hierarchy

When mapping relational fields (`Many2one`, `Many2many`, `One2many`), the engine evaluates lookup strategies in the following prioritized order:

```mermaid
flowchart TD
    A["Source Value (e.g. 'SUP-001' or 'Acme Corp')"] --> B{"Lookup Strategy"}
    B -->|"xml_id"| C["Lookup ir.model.data by External ID"]
    B -->|"record_map"| D["Lookup migration.record.map by Source Key"]
    B -->|"field_search"| E["ORM search([lookup_field, '=', value])"]
    B -->|"domain_expr"| F["Evaluate Custom Domain Expression"]
    
    C & D & E & F --> G{"Record Found?"}
    G -->|"Yes"| H["Return Target Odoo Record ID"]
    G -->|"No"| I{"Auto-Create Enabled?"}
    I -->|"Yes"| J["Create New Target Record on the Fly"]
    I -->|"No"| K["Return False / Raise Validation Warning"]
    J --> H
```

---

## 7. AI Integration & Fault Tolerance

The AI subsystem (`migration.ai.config`) is designed with resilience:
- **Zero Third-Party Dependencies**: Native implementation using Python's standard `urllib.request` and `ssl` modules.
- **Provider Redundancy**: Supports OpenAI, Gemini, Claude, and Local Ollama with identical API interfaces.
- **JSON Mode Guarantee**: Prompts enforce strict JSON output with automatic regex fallback sanitization (`re.search(r'\{.*\}', res, re.DOTALL)`).
- **Timeout & Error Handling**: AI requests are bounded by timeouts with graceful fallback to heuristic defaults if an API quota or network error occurs.
