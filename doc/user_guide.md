# Data Migration Studio - User Guide

This guide provides step-by-step instructions for executing data migrations using **Data Migration Tools Studio** in Odoo 19 and 18.

---

## Table of Contents
1. [Overview & Navigation](#1-overview--navigation)
2. [Configuring AI Assistants](#2-configuring-ai-assistants)
3. [Setting Up Data Connections](#3-setting-up-data-connections)
4. [Building Extraction Queries with Visual Studio & AI](#4-building-extraction-queries-with-visual-studio--ai)
5. [Building Mapping Templates](#5-building-mapping-templates)
6. [Using the Interactive Visual Mapper](#6-using-the-interactive-visual-mapper)
7. [Configuring Transformations & Pipelines](#7-configuring-transformations--pipelines)
8. [Setting Up Validation Rules & Quality Audits](#8-setting-up-validation-rules--quality-audits)
9. [Executing Multi-Stage Migration Plans](#9-executing-multi-stage-migration-plans)
10. [Monitoring, Logs & AI Error Resolution](#10-monitoring-logs--ai-error-resolution)
11. [End-to-End Tutorial: Migrating Contacts with Custom Extraction](#11-end-to-end-tutorial-migrating-contacts-with-custom-extraction)
12. [End-to-End Tutorial: Migrating Products with Variants](#12-end-to-end-tutorial-migrating-products-with-variants)

---

## 1. Overview & Navigation

Access the migration suite from the top-level **Migration Studio** app icon:
- **Dashboard**: Executive overview of active connections, templates, total records migrated, throughput metrics, and recent jobs.
- **ETL Pipeline Setup**:
  - **Migration Plans**: Multi-stage migration projects.
  - **Data Connections**: Source databases, files, APIs, and cloud services.
  - **Extraction Queries**: Visual query builder, field projection studio, delta watermarks, and AI optimization.
  - **Mapping Templates**: Field-to-field mappings and transformation rules.
  - **Transformation Presets**: Reusable transformation pipeline templates.
  - **AI Assistant Settings**: AI LLM provider credentials and model selection.
- **Executions & Audit**:
  - **Plan Execution Runs**: Multi-stage execution history.
  - **Migration Jobs**: Individual ETL job runs.
  - **Audit Logs**: Row-by-row audit stream with raw/transformed JSON payloads.
  - **Record Cross-References**: Cross-system mapping table linking source keys to Odoo records.

---

## 2. Configuring AI Assistants

The module integrates AI capabilities across query building, auto-mapping, data cleansing, validation rule suggestions, and automated error resolution.

1. Navigate to **ETL Pipeline Setup** -> **AI Assistant Settings**.
2. Click **New** and configure:
   - **Provider**: Select OpenAI, Google Gemini, Anthropic Claude, Local Ollama, or Custom OpenAI-compatible endpoint.
   - **API Key**: Enter your provider API key (not required for Ollama).
   - **Model Name**: e.g. `gpt-4o-mini`, `gemini-1.5-flash`, `claude-3-5-sonnet-20241022`, or `llama3`.
   - **Base URL**: e.g. `http://localhost:11434` for Ollama or `https://api.openai.com/v1`.
   - **Default Provider**: Check to make this the system-wide active AI engine.
3. Click **Test AI Connection** in the header to confirm connectivity.

---

## 3. Setting Up Data Connections

1. Navigate to **Data Connections** -> Click **New**.
2. Select your **Connection Type**:

### A. CSV / TSV / Excel / JSON / XML Files
- **Source Method**: File Upload, Server Filesystem Path, or Remote URL.
- **Format Specifics**:
  - CSV: Set Delimiter (e.g. `,`, `;`, `\t`), Quote Character (`"`), and Has Header toggle.
  - Excel: Specify Sheet Name or leave empty for first sheet.
  - JSON: Specify JSON Path to records list (e.g. `data.items` or `results`).
  - XML: Specify XPath query to record elements (e.g. `/root/customer`).

### B. Visual FoxPro DBF Files
- Set File Path to `.dbf` file on server.
- Set Memo File Path to `.fpt` file (if table contains memo fields).

### C. SQL Databases (PostgreSQL, MySQL, SQL Server, SQLite, Oracle, ODBC)
- Configure Host, Port, Database Name, User, and Password.
- Specify default SQL Query (e.g. `SELECT * FROM legacy_customers`).

### D. REST APIs & GraphQL
- Specify URL, HTTP Method (GET, POST), and Authentication (Bearer, Basic, API-Key Header, OAuth2).
- Set Pagination type (Page number, Offset/Limit) and JSON path to items array.
- For GraphQL, write the query payload in the Request Body field.

### E. Cloud Storage & Google Sheets
- **AWS S3**: Bucket name, Object key, Region, Access Key, Secret Key.
- **SFTP**: Host, Port, User, Password, Remote file path.
- **Google Sheets**: Paste published Google Sheets CSV URL.

3. Click **Test Connection & Fetch Schema**:
   - Tests response latency (`latency_ms`).
   - Discovers all column names, tables, and data types.
   - Fetches first 10 rows into the preview tab.

---

## 4. Building Extraction Queries with Visual Studio & AI

Navigate to **ETL Pipeline Setup** -> **Extraction Queries** -> Click **New**:

```
+-----------------------------------------------------------------------------------------+
| [Extraction Query Studio]                                  [AI Assistant] [Run Preview] |
|-----------------------------------------------------------------------------------------|
| [Field Selection]  [WHERE Filters]  [Sorting]  [SQL Query]  [AI Advisor]  [Data Preview]|
|-----------------------------------------------------------------------------------------|
| Tables (Left)     | Table Columns Projection (Center)                                   |
| - customers       | [x] id        -> Target Alias: cust_id       [Type Cast: integer]   |
| - invoices        | [x] full_name -> Target Alias: name          [Type Cast: varchar]   |
| - order_lines     | [x] balance   -> Target Alias: total_due     [Type Cast: float]     |
|                   | [ ] temp_col  (Unchecked - excluded from extraction)                |
+-----------------------------------------------------------------------------------------+
```

### A. Visual Field Selection & Projection
1. Select your **Source Table** from the left panel.
2. Check the columns you want to extract.
3. Enter custom **Target Field Aliases** (e.g. `cust_name` -> `name`). These aliases will automatically flow downstream into your Mapping Templates!
4. Choose **Type Casting** (e.g. `CAST(id AS integer)` or `CAST(write_date AS timestamp)`).

### B. Visual WHERE Filters
1. Switch to the **WHERE Filters** tab.
2. Click **Add Filter Condition**:
   - Choose Field, Operator (`=`, `!=`, `>`, `<`, `LIKE`, `IN`, `IS NOT NULL`).
   - Enter Value or dynamic parameter `:watermark`.
   - Select `AND` / `OR` logical conjunction.

### C. Incremental Delta Watermarks
- Set Extraction Strategy to **Incremental Extraction (Watermark / Delta)**.
- Set **Watermark Source Column** (e.g. `updated_at` or `write_date`).
- Each run automatically tracks the highest value and extracts only modified records in subsequent syncs.

### D. AI Extraction Assistant
Click **AI Assistant** in the top right to access 4 dedicated AI tools:
1. **Natural Language Query Generator**: Type e.g. *"Extract all active partners modified after 2025 where balance > 0"* -> Generates the visual fields, filters, and SQL automatically.
2. **Performance & Index Advisor**: Evaluates the query and generates `CREATE INDEX` recommendations to run on your source database for lightning-fast ETL extraction.
3. **Watermark Advisor**: Inspects columns and sample data to automatically recommend the optimal delta sync column.
4. **Query Explainer & Data Profiler**: Generates an audit report highlighting null risks and potential timezone discrepancies.

### E. Live Data Preview Sandbox
Click **Run Preview** to test your query. Inspect the formatted sample data table with real-time latency (ms) reporting before saving.

---

## 5. Building Mapping Templates

1. Navigate to **Mapping Templates** -> Click **New**.
2. Fill in the header parameters:
   - **Name**: Descriptive title (e.g. `Customers & Contacts Migration`).
   - **Connection**: Select your source connection.
   - **Extraction Query**: Select the Extraction Query configured in Step 4 (optional; brings in custom projected aliases).
   - **Target Odoo Model**: Select target Odoo model (e.g. `res.partner`).
   - **Operation Mode**:
     - `upsert`: Updates existing record if match key exists; creates new record otherwise.
     - `create_only`: Creates new records; skips existing.
     - `update_only`: Updates existing records; skips unmatched rows.
     - `skip_existing`: Skips records that already exist.
   - **Bypass Flags**:
     - *Bypass Tracking*: Disables mail tracking chatter updates for maximum migration speed.
     - *Bypass Subscription*: Prevents sending automatic email notifications to followers.

---

## 6. Using the Interactive Visual Mapper

Switch to the **Visual Diagram Mapper** tab on the template form:

```
+-------------------+      +-------------------+      +-------------------------+
| Sources (Left)    |      | Target (Center)   |      | Pipeline Detail (Right) |
|-------------------|      |-------------------|      |-------------------------|
| [o] customer_name ----------> [o] name       |      | 1. Trim Whitespace      |
| [o] email_address ----------> [o] email      |      | 2. Capitalize           |
| [o] phone_number  ----------> [o] phone      |      | [Test Live Sample]      |
| [o] country_code  ----------> [o] country_id |      |                         |
+-------------------+      +-------------------+      +-------------------------+
```

1. **Auto-Map**: Click **Auto-Map** in the header to instantly match fields with identical names.
2. **AI Auto-Map**: Click **AI Auto-Map** to let LLM analyze semantics (e.g., automatically matching `cust_tel` -> `phone` and `tax_reg_no` -> `vat`).
3. **Manual Connection**: Drag a source column port on the left and drop it onto a target field port in the center.
4. **Configure Match Keys**: Toggle **Use as Unique Match Key** on identifier fields (e.g. `code` -> `ref` or `email`).
5. **Save Mappings**: Click **Save Field Mappings** in the top right to commit your configuration.

---

## 7. Configuring Transformations & Pipelines

In the right-hand panel of the Visual Mapper (or in the Mapping Line detail form), you can chain multiple sequential transformation steps:

### Cleansing Examples
- **Clean Phone Numbers**: Add Cleansing (`regex`, pattern: `[^\d+]`, replace: `""`) -> Cleansing (`trim`).
- **Standardize Names**: Add Cleansing (`trim`) -> Cleansing (`title`).
- **Null Safety**: Add Cleansing (`handle_null`, fallback: `"N/A"`).

### Date Standardizer Examples
- **Legacy Date Conversion**: Input Date Format: `%d/%m/%Y`, Target Format: `%Y-%m-%d`.

### Unit Conversions Examples
- **Weight Conversion**: Mass (lb -> kg).
- **Temperature Conversion**: Temperature (°F -> °C).

### Python Expressions Sandbox
For complex custom logic, choose **Python Expression**:
```python
# Available variables: value, record (dict of entire row), datetime, re, json
if record.get('is_company') == '1':
    result = 'company'
else:
    result = 'person'
```

### AI Prompt NLP Transformer
For unstructured text normalization:
```
Extract the 2-letter ISO country code from this freeform address text: {value}
```

---

## 8. Setting Up Validation Rules & Quality Audits

Switch to the **Validation Rules** tab on your template:

1. Click **AI Suggest Rules** to let AI analyze source columns and propose standard validation rules.
2. Add manual rules:
   - **Mandatory Rule**: Ensures vital fields (like `name`) are present.
   - **Regex Rule**: Validates email format: `^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$`.
   - **Range Check**: Ensures numeric fields like `standard_price >= 0`.
   - **Foreign Key Check**: Ensures `parent_id` exists in `res.partner`.
3. Set **Action on Failure**:
   - `warning`: Record warning in audit log, but proceed with record loading.
   - `reject_record`: Skip loading this specific row, record error log, and continue with batch.
   - `abort_stage`: Halt the entire migration stage immediately.
4. Click **Audit Data Quality**: Computes a 0–100% Quality Health Score auditing null ratios, duplicates, and invalid formats before migration.

---

## 9. Executing Multi-Stage Migration Plans

1. Navigate to **Migration Plans** -> Click **New**.
2. Structure your Stages and Steps:
   - **Stage 1: Base Reference Data**: Step 1: Partner Categories, Step 2: Payment Terms.
   - **Stage 2: Master Data**: Step 1: Customer Partners, Step 2: Vendor Partners.
   - **Stage 3: Products**: Step 1: Product Categories, Step 2: Product Templates.
3. Click **Pre-Flight Check**:
   - Automatically validates all connections, model definitions, key fields, and active templates.
4. Click **Execute Plan** -> Launch Execution Wizard:
   - **Dry-Run Simulation**: Runs the entire extraction, transformation, validation, and loading pipeline inside a database savepoint that rolls back upon completion. Zero database changes are made, allowing 100% safe verification.
   - **Live Execution**: Commits all valid records to Odoo.
5. Watch live progress in the **OWL 3 Plan Console**.

---

## 10. Monitoring, Logs & AI Error Resolution

1. Navigate to **Executions & Audit** -> **Audit Logs**.
2. Filter by **Errors Only** or **Warnings**.
3. Open any Error Log to inspect:
   - Raw source row JSON.
   - Transformed values dictionary.
   - Full Python error traceback.
4. Click **Ask AI for Fix Suggestion**:
   - AI analyzes the traceback and source row.
   - Generates plain-English root-cause analysis and exact mapping fix instructions.

---

## 11. End-to-End Tutorial: Migrating Contacts with Custom Extraction

### Scenario: Migrating SQL Server `legacy_customers` to `res.partner`

1. **Create Data Connection**:
   - Name: `Legacy SQL Server`.
   - Type: `Direct SQL Database` -> Select `mssql`, host, port, and credentials.
   - Test Connection.
2. **Build Extraction Query**:
   - Go to **Extraction Queries** -> New -> Name: `Active Customers Extraction`.
   - Connection: `Legacy SQL Server`.
   - Strategy: `Incremental Extraction (Watermark / Delta)` -> Watermark Column: `updated_at`.
   - In **Visual Query Studio**: Pick `customers` table -> Select `cust_id` (Alias: `ref`), `company_name` (Alias: `name`), `email`, `phone`, `updated_at`.
   - In **WHERE Filters**: Add `status = 'ACTIVE'`.
   - Run **Live Preview** -> Verify 10 rows. Save.
3. **Create Mapping Template**:
   - Name: `SQL Customers to Odoo Partners`.
   - Connection: `Legacy SQL Server` -> Extraction Query: `Active Customers Extraction`.
   - Target Model: `Contact (res.partner)`.
   - Click **AI Auto-Map** in the Visual Mapper tab.
   - Mark `ref` as **Match Key**.
4. **Run Simulation & Live Sync**:
   - Execute Dry-Run Simulation. Verify 0 errors.
   - Run Live Job -> Inspect records in **Contacts** app. Subsequent runs extract only new/updated contacts!

---

## 12. End-to-End Tutorial: Migrating Products with Variants

### Scenario: Migrating `products.xlsx` to `product.template`

1. **Create Connection**:
   - Name: `Product Master Excel`.
   - Type: `Excel File` -> Upload `.xlsx`.
2. **Create Template**:
   - Target Model: `Product (product.template)`.
   - Operation Mode: `upsert`.
3. **Map Fields**:
   - `sku` -> `default_code` (Match Key).
   - `item_name` -> `name`.
   - `weight_lbs` -> `weight` (Unit conversion: `lb -> kg`).
   - `cost_usd` -> `standard_price`.
   - `retail_usd` -> `list_price`.
   - `category` -> `categ_id` (Lookup Strategy: `field_search` by `name`, toggle `auto_create`).
4. **Validation Rules**:
   - Mandatory `name`.
   - Numeric range `list_price >= 0`.
5. **Execute Plan**:
   - Run execution -> Verify products in **Inventory** -> **Products**.
