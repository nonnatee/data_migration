# Data Migration Studio - User Guide

This guide provides step-by-step instructions for executing data migrations using **Data Migration Tools Studio** in Odoo 19 and 18.

---

## Table of Contents
1. [Overview & Navigation](#1-overview--navigation)
2. [Configuring AI Assistants](#2-configuring-ai-assistants)
3. [Setting Up Data Connections](#3-setting-up-data-connections)
4. [Building Mapping Templates](#4-building-mapping-templates)
5. [Using the Interactive Visual Mapper](#5-using-the-interactive-visual-mapper)
6. [Configuring Transformations & Pipelines](#6-configuring-transformations--pipelines)
7. [Setting Up Validation Rules & Quality Audits](#7-setting-up-validation-rules--quality-audits)
8. [Executing Multi-Stage Migration Plans](#8-executing-multi-stage-migration-plans)
9. [Monitoring, Logs & AI Error Resolution](#9-monitoring-logs--ai-error-resolution)
10. [End-to-End Tutorial: Migrating Contacts](#10-end-to-end-tutorial-migrating-contacts)
11. [End-to-End Tutorial: Migrating Products with Variants](#11-end-to-end-tutorial-migrating-products-with-variants)

---

## 1. Overview & Navigation

Access the migration suite from the top-level **Migration Studio** app icon:
- **Dashboard**: Executive overview of active connections, templates, total records migrated, throughput metrics, and recent jobs.
- **ETL Pipeline Setup**:
  - **Migration Plans**: Multi-stage migration projects.
  - **Data Connections**: Source databases, files, APIs, and cloud services.
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

The module integrates AI capabilities across auto-mapping, data cleansing, validation rule suggestions, and automated error resolution.

1. Navigate to **ETL Pipeline Setup** -> **AI Assistant Settings**.
2. Click **New** and configure:
   - **Provider**: Select OpenAI, Google Gemini, Anthropic Claude, Local Ollama, or Custom OpenAI-compatible endpoint.
   - **API Key**: Enter your provider API key (not required for Ollama).
   - **Model Name**: e.g. `gpt-4o`, `gemini-1.5-pro`, `claude-3-5-sonnet-20241022`, or `llama3`.
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
- Specify SQL Query (e.g. `SELECT * FROM legacy_customers WHERE active = 1`).

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
   - Discovers all column names and data types.
   - Fetches first 10 rows into the preview tab.

---

## 4. Building Mapping Templates

1. Navigate to **Mapping Templates** -> Click **New**.
2. Fill in the header parameters:
   - **Name**: Descriptive title (e.g. `Customers & Contacts Migration`).
   - **Connection**: Select the connection configured in Step 3.
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

## 5. Using the Interactive Visual Mapper

Switch to the **Visual Diagram Mapper** tab on the template form to use the OWL 3 canvas:

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

## 6. Configuring Transformations & Pipelines

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

## 7. Setting Up Validation Rules & Quality Audits

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

## 8. Executing Multi-Stage Migration Plans

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

## 9. Monitoring, Logs & AI Error Resolution

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

## 10. End-to-End Tutorial: Migrating Contacts

### Scenario: Migrating `customers.csv` to `res.partner`

1. **Create Connection**:
   - Name: `Legacy Customer CSV`.
   - Type: `CSV File` -> Upload `customers.csv`.
   - Test Connection.
2. **Create Template**:
   - Name: `Customer Partners Template`.
   - Target Model: `Contact (res.partner)`.
   - Operation Mode: `upsert`.
3. **Map Fields**:
   - `customer_id` -> `ref` (Check **Match Key**).
   - `company_name` -> `name`.
   - `email_addr` -> `email`.
   - `phone_no` -> `phone` (Add regex transform `[^\d+]`).
   - `country` -> `country_id` (Lookup Strategy: `field_search` by `code`).
4. **Run Simulation**:
   - Click **Run Migration Job** -> Verify 0 errors in dry-run mode.
5. **Execute Live**:
   - Run live job. Inspect newly created partners in **Contacts** app.

---

## 11. End-to-End Tutorial: Migrating Products with Variants

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
