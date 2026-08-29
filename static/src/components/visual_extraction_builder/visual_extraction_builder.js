/** @odoo-module **/

import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class VisualExtractionBuilder extends Component {
    static template = "data_migration.VisualExtractionBuilder";
    static props = {
        record: { type: Object, optional: true },
        resId: { type: Number, optional: true },
        readonly: { type: Boolean, optional: true },
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            isLoading: true,
            isSaving: false,
            isRunningPreview: false,
            isAiProcessing: false,
            activeTab: "visual", // 'visual', 'filters', 'sorting', 'query', 'ai', 'preview'

            // Record data
            extractionId: null,
            name: "",
            connType: "file_csv",
            connectionName: "",
            extractionType: "full",
            useVisualBuilder: true,

            // Watermark
            watermarkColumn: "",
            lastWatermarkValue: "",
            watermarkDatatype: "datetime",

            // Schema & Visual Builder State
            tables: [],
            selectedTable: "source_table",
            tableSearch: "",
            fieldSearch: "",
            selectedFields: [],
            whereClauses: [],
            sortClauses: [],

            // Query strings
            customQuery: "",
            compiledQuery: "",

            // AI & Optimization
            aiTab: "generate", // 'generate', 'optimize', 'watermark', 'explain'
            aiPrompt: "",
            aiOptimizationNotes: "",
            aiExplanation: "",

            // Preview Data
            previewRecords: [],
            previewColumns: [],
            previewLatency: 0.0,
            previewError: null,
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    get resId() {
        if (this.props.record) {
            if (this.props.record.resId) return this.props.record.resId;
            if (this.props.record.data && this.props.record.data.id) return this.props.record.data.id;
            if (typeof this.props.record.id === "number") return this.props.record.id;
        }
        return this.props.resId || null;
    }

    async loadData() {
        const id = this.resId;
        if (!id) {
            this.state.isLoading = false;
            return;
        }
        this.state.isLoading = true;
        try {
            const data = await this.orm.call("migration.extraction", "get_visual_builder_data", [[id]]);
            this.state.extractionId = data.id;
            this.state.name = data.name;
            this.state.connType = data.conn_type;
            this.state.connectionName = data.connection_name;
            this.state.extractionType = data.extraction_type;
            this.state.useVisualBuilder = data.use_visual_builder;
            this.state.watermarkColumn = data.watermark_column || "";
            this.state.lastWatermarkValue = data.last_watermark_value || "";
            this.state.watermarkDatatype = data.watermark_datatype || "datetime";
            this.state.selectedTable = data.selected_table || "source_table";
            this.state.selectedFields = data.selected_fields || [];
            this.state.whereClauses = data.where_clauses || [];
            this.state.sortClauses = data.sort_clauses || [];
            this.state.customQuery = data.custom_query || "";
            this.state.compiledQuery = data.compiled_query || "";
            this.state.aiOptimizationNotes = data.ai_optimization_notes || "";
            this.state.aiExplanation = data.ai_explanation || "";
            this.state.previewRecords = data.preview_data || [];
            this.state.previewLatency = data.latency_ms || 0.0;

            // Process Schema
            const schema = data.schema || { tables: [] };
            this.state.tables = schema.tables || [];

            // If tables exist and selectedTable is default or empty, pick first table
            if (this.state.tables.length > 0 && (!this.state.selectedTable || this.state.selectedTable === "source_table")) {
                this.state.selectedTable = this.state.tables[0].name;
            }

            // Sync available fields from current selected table if selectedFields is empty
            this.syncFieldsFromCurrentTable();

            // Set preview columns
            if (this.state.previewRecords.length > 0) {
                this.state.previewColumns = Object.keys(this.state.previewRecords[0]);
            }
        } catch (err) {
            console.error("Failed to load extraction builder data:", err);
            this.notification.add(`Error loading extraction schema: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isLoading = false;
        }
    }

    getCurrentTableDef() {
        return this.state.tables.find((t) => t.name === this.state.selectedTable) || null;
    }

    syncFieldsFromCurrentTable() {
        const currentTable = this.getCurrentTableDef();
        if (!currentTable || !currentTable.columns) return;

        const existingMap = new Map();
        for (const f of this.state.selectedFields) {
            existingMap.set(f.field, f);
        }

        const newSelectedFields = [];
        for (const col of currentTable.columns) {
            if (existingMap.has(col.name)) {
                newSelectedFields.push(existingMap.get(col.name));
            } else {
                newSelectedFields.push({
                    field: col.name,
                    alias: col.name,
                    cast: "none",
                    selected: true,
                    type: col.type || "varchar",
                    is_pk: Boolean(col.is_pk),
                });
            }
        }

        if (newSelectedFields.length > 0) {
            this.state.selectedFields = newSelectedFields;
        }
    }

    // ------------------------------------------------------------
    // GETTERS & COMPUTED PROPERTIES
    // ------------------------------------------------------------

    get filteredTables() {
        if (!this.state.tableSearch) {
            return this.state.tables;
        }
        const q = this.state.tableSearch.toLowerCase();
        return this.state.tables.filter((t) => t.name.toLowerCase().includes(q));
    }

    get filteredSelectedFields() {
        if (!this.state.fieldSearch) {
            return this.state.selectedFields;
        }
        const q = this.state.fieldSearch.toLowerCase();
        return this.state.selectedFields.filter(
            (f) => f.field.toLowerCase().includes(q) || (f.alias && f.alias.toLowerCase().includes(q))
        );
    }

    get selectedFieldsCount() {
        return this.state.selectedFields.filter((f) => f.selected).length;
    }

    // ------------------------------------------------------------
    // NAVIGATION & UI HANDLERS
    // ------------------------------------------------------------

    setTab(tabName) {
        this.state.activeTab = tabName;
    }

    openAiAssistant(subTab = "generate") {
        this.state.activeTab = "ai";
        this.state.aiTab = subTab;
    }

    setAiTab(aiTabName) {
        this.state.aiTab = aiTabName;
    }

    onToggleVisualBuilder(ev) {
        this.state.useVisualBuilder = ev.target.checked;
        this.recomputeCompiledQuery();
    }

    onCustomQueryChange(ev) {
        if (!this.state.useVisualBuilder) {
            this.state.customQuery = ev.target.value;
            this.recomputeCompiledQuery();
        }
    }

    formatCell(row, col) {
        const val = row[col];
        if (val === undefined || val === null) {
            return "";
        }
        if (typeof val === "object") {
            return JSON.stringify(val);
        }
        return String(val);
    }

    // ------------------------------------------------------------
    // TABLE & FIELD ACTIONS
    // ------------------------------------------------------------

    selectTable(table) {
        this.state.selectedTable = table.name;
        this.syncFieldsFromCurrentTable();
        this.recomputeCompiledQuery();
    }

    toggleField(field) {
        field.selected = !field.selected;
        this.recomputeCompiledQuery();
    }

    selectAllFields(selected = true) {
        for (const f of this.state.selectedFields) {
            f.selected = selected;
        }
        this.recomputeCompiledQuery();
    }

    updateFieldAlias(field, newAlias) {
        field.alias = newAlias;
        this.recomputeCompiledQuery();
    }

    updateFieldCast(field, newCast) {
        field.cast = newCast;
        this.recomputeCompiledQuery();
    }

    // ------------------------------------------------------------
    // WHERE CLAUSES
    // ------------------------------------------------------------

    addWhereClause() {
        const availableCols = this.state.selectedFields.map((f) => f.field);
        const defaultField = availableCols[0] || "id";
        this.state.whereClauses.push({
            field: defaultField,
            operator: "=",
            value: "",
            conjunction: "AND",
        });
        this.recomputeCompiledQuery();
    }

    removeWhereClause(index) {
        this.state.whereClauses.splice(index, 1);
        this.recomputeCompiledQuery();
    }

    updateWhereClause(index, key, value) {
        if (this.state.whereClauses[index]) {
            this.state.whereClauses[index][key] = value;
            this.recomputeCompiledQuery();
        }
    }

    // ------------------------------------------------------------
    // SORT CLAUSES
    // ------------------------------------------------------------

    addSortClause() {
        const availableCols = this.state.selectedFields.map((f) => f.field);
        const defaultField = availableCols[0] || "id";
        this.state.sortClauses.push({
            field: defaultField,
            direction: "ASC",
        });
        this.recomputeCompiledQuery();
    }

    removeSortClause(index) {
        this.state.sortClauses.splice(index, 1);
        this.recomputeCompiledQuery();
    }

    updateSortClause(index, key, value) {
        if (this.state.sortClauses[index]) {
            this.state.sortClauses[index][key] = value;
            this.recomputeCompiledQuery();
        }
    }

    // ------------------------------------------------------------
    // COMPILED QUERY CLIENT-SIDE GENERATOR
    // ------------------------------------------------------------

    recomputeCompiledQuery() {
        if (!this.state.useVisualBuilder && this.state.customQuery) {
            this.state.compiledQuery = this.state.customQuery;
            return;
        }

        const table = this.state.selectedTable || "source_table";
        const activeFields = this.state.selectedFields.filter((f) => f.selected);

        let selectClause = "*";
        if (activeFields.length > 0) {
            selectClause = activeFields
                .map((f) => {
                    let expr = f.field;
                    if (f.cast && f.cast !== "none" && f.cast !== "default") {
                        expr = `CAST(${f.field} AS ${f.cast})`;
                    }
                    if (f.alias && f.alias !== f.field) {
                        return `${expr} AS ${f.alias}`;
                    }
                    return expr;
                })
                .join(", ");
        }

        const whereParts = [];
        this.state.whereClauses.forEach((c, idx) => {
            if (!c.field) return;
            let cond = "";
            if (c.operator === "IS NULL" || c.operator === "IS NOT NULL") {
                cond = `${c.field} ${c.operator}`;
            } else if (c.operator === "IN") {
                cond = `${c.field} IN (${c.value})`;
            } else if (c.operator === "LIKE" || c.operator === "ILIKE") {
                cond = `${c.field} ${c.operator} '${c.value}'`;
            } else if (c.value && c.value.toLowerCase() === ":watermark") {
                cond = `${c.field} > :watermark`;
            } else if (c.value && (!isNaN(Number(c.value)) || ["true", "false"].includes(c.value.toLowerCase()))) {
                cond = `${c.field} ${c.operator} ${c.value}`;
            } else {
                cond = `${c.field} ${c.operator} '${c.value || ""}'`;
            }

            if (idx > 0 && whereParts.length > 0) {
                whereParts.push(`${c.conjunction || "AND"} ${cond}`);
            } else {
                whereParts.push(cond);
            }
        });

        const sortParts = this.state.sortClauses
            .filter((s) => s.field)
            .map((s) => `${s.field} ${s.direction || "ASC"}`);

        let sql = `SELECT ${selectClause}\nFROM ${table}`;
        if (whereParts.length > 0) {
            sql += `\nWHERE ${whereParts.join(" ")}`;
        }
        if (sortParts.length > 0) {
            sql += `\nORDER BY ${sortParts.join(", ")}`;
        }

        this.state.compiledQuery = sql;
    }

    // ------------------------------------------------------------
    // SAVE & PREVIEW
    // ------------------------------------------------------------

    async saveAll() {
        const id = this.resId;
        if (!id) return;

        this.state.isSaving = true;
        try {
            const dataToSave = {
                selected_table: this.state.selectedTable,
                selected_fields: this.state.selectedFields,
                where_clauses: this.state.whereClauses,
                sort_clauses: this.state.sortClauses,
                custom_query: this.state.customQuery,
                use_visual_builder: this.state.useVisualBuilder,
                watermark_column: this.state.watermarkColumn,
                extraction_type: this.state.extractionType,
            };

            await this.orm.call("migration.extraction", "save_visual_builder_data", [[id], dataToSave]);
            this.notification.add("Extraction query configuration saved successfully!", { type: "success" });
            await this.loadData();
        } catch (err) {
            console.error("Failed to save extraction builder data:", err);
            this.notification.add(`Save failed: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isSaving = false;
        }
    }

    async runPreview() {
        const id = this.resId;
        if (!id) return;

        // Auto save first
        await this.saveAll();

        this.state.isRunningPreview = true;
        this.state.previewError = null;
        try {
            const res = await this.orm.call("migration.extraction", "run_preview_extraction", [[id], 10]);
            if (res.success) {
                this.state.previewRecords = res.records || [];
                this.state.previewColumns = res.columns || [];
                this.state.previewLatency = res.latency_ms || 0.0;
                this.state.activeTab = "preview";
                this.notification.add(`Preview extracted ${res.total_extracted} records in ${res.latency_ms} ms`, { type: "success" });
            } else {
                this.state.previewError = res.error;
                this.notification.add(`Preview failed: ${res.error}`, { type: "danger" });
            }
        } catch (err) {
            this.state.previewError = err.message || String(err);
            this.notification.add(`Execution error: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isRunningPreview = false;
        }
    }

    // ------------------------------------------------------------
    // AI INTEGRATION ACTIONS
    // ------------------------------------------------------------

    async callAiGenerate() {
        if (!this.state.aiPrompt.trim()) {
            this.notification.add("Please describe what data you want to extract.", { type: "warning" });
            return;
        }
        const id = this.resId;
        if (!id) return;

        this.state.isAiProcessing = true;
        try {
            const res = await this.orm.call("migration.extraction", "action_ai_generate_query", [[id], this.state.aiPrompt]);
            this.notification.add("AI extraction query generated!", { type: "success" });
            await this.loadData();
            this.state.activeTab = "visual";
        } catch (err) {
            console.error("AI Generation Error:", err);
            this.notification.add(`AI error: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isAiProcessing = false;
        }
    }

    async callAiOptimize() {
        const id = this.resId;
        if (!id) return;

        this.state.isAiProcessing = true;
        try {
            const res = await this.orm.call("migration.extraction", "action_ai_optimize_query", [[id]]);
            this.state.aiOptimizationNotes = res.notes || "";
            this.notification.add("AI performance analysis and indexing advice ready!", { type: "success" });
            this.state.aiTab = "optimize";
            this.state.activeTab = "ai";
        } catch (err) {
            console.error("AI Optimize Error:", err);
            this.notification.add(`AI optimization error: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isAiProcessing = false;
        }
    }

    async callAiAdviseWatermark() {
        const id = this.resId;
        if (!id) return;

        this.state.isAiProcessing = true;
        try {
            const res = await this.orm.call("migration.extraction", "action_ai_advise_watermark", [[id]]);
            this.state.watermarkColumn = res.watermark_column;
            this.state.watermarkDatatype = res.watermark_datatype;
            this.notification.add(`AI recommended watermark column: ${res.watermark_column}`, { type: "success" });
            await this.loadData();
        } catch (err) {
            console.error("AI Watermark Advisor Error:", err);
            this.notification.add(`Watermark advisor error: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isAiProcessing = false;
        }
    }

    async callAiExplain() {
        const id = this.resId;
        if (!id) return;

        this.state.isAiProcessing = true;
        try {
            const res = await this.orm.call("migration.extraction", "action_ai_explain_query", [[id]]);
            this.state.aiExplanation = res.explanation || "";
            this.notification.add("AI query explanation and risk profile ready!", { type: "success" });
            this.state.aiTab = "explain";
            this.state.activeTab = "ai";
        } catch (err) {
            console.error("AI Explain Error:", err);
            this.notification.add(`Explain error: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isAiProcessing = false;
        }
    }
}

registry.category("view_widgets").add("visual_extraction_builder", {
    component: VisualExtractionBuilder,
});
