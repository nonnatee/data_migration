/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class VisualMapperWidget extends Component {
    static template = "data_migration.VisualMapperWidget";
    static props = {
        record: { type: Object, optional: true },
        resId: { type: Number, optional: true },
        readonly: { type: Boolean, optional: true },
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.svgRef = useRef("svgCanvas");
        this.containerRef = useRef("mapperContainer");
        this.sourceListRef = useRef("sourceList");
        this.targetListRef = useRef("targetList");

        this.state = useState({
            isLoading: true,
            isSaving: false,
            activeMode: "transform", // 'transform' or 'mapping'
            templateId: null,
            templateName: "",
            connectionName: "",
            targetModelName: "",
            rawColumns: [],
            availableVariables: [],
            targetFields: [],
            transformations: [],
            mappings: [],
            transformPresets: [],

            // Filter queries
            sourceSearch: "",
            targetSearch: "",

            // Selection
            selectedSourceCol: null,
            selectedTransformIndex: 0,
            selectedPresetId: "",

            // Drag and drop state for mapping mode
            dragSourceCol: null,
            dragOverTargetId: null,
            dragMousePos: { x: 0, y: 0 },

            // Interactive test sandbox
            sampleInput: " 150.50 lbs ",
            sampleResult: null,
            isTestingSample: false,
        });

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            this.onResizeBound = () => this.updateSvgLines();
            window.addEventListener("resize", this.onResizeBound);
            this.updateSvgLines();
        });

        onWillUnmount(() => {
            if (this.onResizeBound) {
                window.removeEventListener("resize", this.onResizeBound);
            }
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
            const data = await this.orm.call("migration.template", "action_get_visual_mapping_data", [[id]]);
            this.state.templateId = data.template_id;
            this.state.templateName = data.template_name;
            this.state.connectionName = data.connection_name;
            this.state.targetModelName = data.target_model_name;
            this.state.rawColumns = data.raw_columns || [];
            this.state.targetFields = data.target_fields || [];
            this.state.transformations = data.transformations || [];
            this.state.mappings = data.mappings || [];
            this.state.transformPresets = data.transform_presets || [];

            this.updateDerivedVariables();

            if (this.state.rawColumns.length > 0 && !this.state.selectedSourceCol) {
                this.state.selectedSourceCol = this.state.rawColumns[0];
            }
        } catch (err) {
            console.error("Failed to load visual mapper data:", err);
            this.notification.add(`Error loading data: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isLoading = false;
            setTimeout(() => this.updateSvgLines(), 100);
        }
    }

    switchMode(mode) {
        this.state.activeMode = mode;
        this.updateDerivedVariables();
        if (mode === "mapping") {
            setTimeout(() => this.updateSvgLines(), 100);
        }
    }

    updateDerivedVariables() {
        const raw = this.state.rawColumns || [];
        const derived = this.state.transformations
            .map(t => (t.output_field || "").trim())
            .filter(f => f.length > 0);
        this.state.availableVariables = Array.from(new Set([...raw, ...derived]));
    }

    isVariableDerived(varName) {
        return !this.state.rawColumns.includes(varName);
    }

    isSourceMapped(varName) {
        return this.state.mappings.some(m => m.source_field === varName);
    }

    getMappingForField(targetFieldId) {
        return this.state.mappings.find(m => m.target_field_id === targetFieldId);
    }

    get filteredRawColumns() {
        let cols = this.state.rawColumns;
        if (!this.state.sourceSearch) return cols;
        const q = this.state.sourceSearch.toLowerCase();
        return cols.filter(c => c.toLowerCase().includes(q));
    }

    get filteredAvailableVariables() {
        let vars = this.state.availableVariables;
        if (!this.state.sourceSearch) return vars;
        const q = this.state.sourceSearch.toLowerCase();
        return vars.filter(v => v.toLowerCase().includes(q));
    }

    get filteredTargetFields() {
        let fields = this.state.targetFields;
        if (!this.state.targetSearch) return fields;
        const q = this.state.targetSearch.toLowerCase();
        return fields.filter(f => (f.name && f.name.toLowerCase().includes(q)) || (f.field_description && f.field_description.toLowerCase().includes(q)));
    }

    // ------------------------------------------------------------
    // MODE 1: TRANSFORMATION STUDIO METHODS
    // ------------------------------------------------------------

    addNewTransformation() {
        const src = this.state.selectedSourceCol || (this.state.rawColumns[0] || "col1");
        this.state.transformations.push({
            sequence: (this.state.transformations.length + 1) * 10,
            source_field: src,
            output_field: src,
            transform_category: "cleansing",
            cleansing_type: "trim",
            pad_char: "0",
            pad_count: 10,
            regex_pattern: "",
            regex_replace: "",
            input_date_format: "%Y-%m-%d",
            output_date_format: "%Y-%m-%d",
            unit_type: "mass",
            source_unit: "kg",
            target_unit: "lb",
            custom_scale_ratio: 1.0,
            target_type: "string",
            math_op: "add",
            math_operand: 0.0,
            default_fallback: "",
            ai_prompt_template: "",
            python_code: "",
        });
        this.updateDerivedVariables();
    }

    addTransformForColumn(col) {
        this.state.selectedSourceCol = col;
        this.state.transformations.push({
            sequence: (this.state.transformations.length + 1) * 10,
            source_field: col,
            output_field: col,
            transform_category: "cleansing",
            cleansing_type: "trim",
        });
        this.updateDerivedVariables();
        this.notification.add(`Added cleansing transformation for '${col}'`, { type: "info" });
    }

    removeTransform(index) {
        this.state.transformations.splice(index, 1);
        this.updateDerivedVariables();
    }

    moveTransform(index, direction) {
        const newIndex = index + direction;
        if (newIndex < 0 || newIndex >= this.state.transformations.length) return;
        const item = this.state.transformations.splice(index, 1)[0];
        this.state.transformations.splice(newIndex, 0, item);
    }

    async applyTransformPreset() {
        const presetId = this.state.selectedPresetId;
        if (!presetId) return;

        try {
            const preset = await this.orm.read("migration.transform.template", [parseInt(presetId)], ["name", "category", "step_ids"]);
            if (!preset || !preset[0]) return;
            const steps = await this.orm.read("migration.transform.template.step", preset[0].step_ids, [
                "sequence", "transform_category", "cleansing_type", "regex_pattern", "regex_replace", "unit_type", "source_unit", "target_unit"
            ]);

            const src = this.state.selectedSourceCol || (this.state.rawColumns[0] || "col1");
            for (const s of steps) {
                this.state.transformations.push({
                    sequence: (this.state.transformations.length + 1) * 10,
                    source_field: src,
                    output_field: src,
                    transform_category: s.transform_category || "cleansing",
                    cleansing_type: s.cleansing_type || "trim",
                    regex_pattern: s.regex_pattern || "",
                    regex_replace: s.regex_replace || "",
                    unit_type: s.unit_type || "mass",
                    source_unit: s.source_unit || "kg",
                    target_unit: s.target_unit || "lb",
                });
            }
            this.updateDerivedVariables();
            this.notification.add(`Applied preset '${preset[0].name}' (${steps.length} steps).`, { type: "success" });
            this.state.selectedPresetId = "";
        } catch (err) {
            console.error("Failed to apply preset:", err);
            this.notification.add(`Preset error: ${err.message || err}`, { type: "danger" });
        }
    }

    testSampleTransform() {
        this.state.isTestingSample = true;
        try {
            let val = this.state.sampleInput;
            for (const t of this.state.transformations) {
                val = this.evaluateSingleTransformClient(val, t);
            }
            this.state.sampleResult = JSON.stringify(val);
        } catch (e) {
            this.state.sampleResult = `Error: ${e.message || e}`;
        } finally {
            this.state.isTestingSample = false;
        }
    }

    evaluateSingleTransformClient(val, t) {
        if (t.transform_category === "cleansing") {
            const s = String(val);
            if (t.cleansing_type === "trim") return s.trim();
            if (t.cleansing_type === "upper") return s.toUpperCase();
            if (t.cleansing_type === "lower") return s.toLowerCase();
            if (t.cleansing_type === "regex" && t.regex_pattern) {
                return s.replace(new RegExp(t.regex_pattern, "g"), t.regex_replace || "");
            }
            if (t.cleansing_type === "strip_non_numeric") return s.replace(/[^\d.]/g, "");
            return s.trim();
        } else if (t.transform_category === "math_expr") {
            const n = parseFloat(val) || 0;
            const op = t.math_operand || 0;
            if (t.math_op === "add") return n + op;
            if (t.math_op === "subtract") return n - op;
            if (t.math_op === "multiply") return n * op;
            if (t.math_op === "divide" && op !== 0) return n / op;
            return n;
        } else if (t.transform_category === "slugify") {
            return String(val).toLowerCase().replace(/[^\w\s-]/g, "").replace(/[-\s]+/g, "_");
        }
        return val;
    }

    // ------------------------------------------------------------
    // MODE 2: TARGET FIELD MAPPER METHODS & DRAG-AND-DROP
    // ------------------------------------------------------------

    selectSource(col) {
        this.state.selectedSourceCol = col;
    }

    onSourceDragStart(event, colName) {
        this.state.dragSourceCol = colName;
        event.dataTransfer.setData("text/plain", colName);
        event.dataTransfer.effectAllowed = "link";
    }

    onDragEnd() {
        this.state.dragSourceCol = null;
        this.state.dragOverTargetId = null;
    }

    onTargetDragOver(event, targetId) {
        event.preventDefault();
        event.dataTransfer.dropEffect = "link";
        this.state.dragOverTargetId = targetId;
    }

    onTargetDragLeave(targetId) {
        if (this.state.dragOverTargetId === targetId) {
            this.state.dragOverTargetId = null;
        }
    }

    onTargetDrop(event, targetField) {
        event.preventDefault();
        const srcCol = event.dataTransfer.getData("text/plain") || this.state.dragSourceCol;
        this.state.dragOverTargetId = null;
        this.state.dragSourceCol = null;

        if (!srcCol || !targetField) return;

        // Check if this target field already has a mapping line
        let existing = this.state.mappings.find(m => m.target_field_id === targetField.id);
        if (existing) {
            existing.source_field = srcCol;
        } else {
            this.state.mappings.push({
                sequence: (this.state.mappings.length + 1) * 10,
                source_field: srcCol,
                target_field_id: targetField.id,
                target_field_name: targetField.name,
                target_field_ttype: targetField.ttype,
                default_value: "",
                is_key_field: ["id", "code", "ref", "default_code", "email", "vat"].includes(targetField.name),
                lookup_strategy: "field_search",
            });
        }

        this.notification.add(`Mapped '${srcCol}' -> '${targetField.name}'`, { type: "info" });
        setTimeout(() => this.updateSvgLines(), 50);
    }

    toggleKeyField(mapping) {
        mapping.is_key_field = !mapping.is_key_field;
    }

    removeMapping(mapping) {
        const idx = this.state.mappings.indexOf(mapping);
        if (idx >= 0) {
            this.state.mappings.splice(idx, 1);
            setTimeout(() => this.updateSvgLines(), 50);
        }
    }

    clearAllMappings() {
        this.state.mappings = [];
        setTimeout(() => this.updateSvgLines(), 50);
    }

    autoMapMatching() {
        const vars = this.state.availableVariables;
        const fields = this.state.targetFields;
        let count = 0;

        for (const v of vars) {
            const vClean = v.toLowerCase().replace(/[\s-_]+/g, "");
            const match = fields.find(f => {
                const fClean = f.name.toLowerCase().replace(/[\s-_]+/g, "");
                const labelClean = (f.field_description || "").toLowerCase().replace(/[\s-_]+/g, "");
                return fClean === vClean || labelClean === vClean;
            });

            if (match && !this.state.mappings.some(m => m.target_field_id === match.id)) {
                this.state.mappings.push({
                    sequence: (this.state.mappings.length + 1) * 10,
                    source_field: v,
                    target_field_id: match.id,
                    target_field_name: match.name,
                    target_field_ttype: match.ttype,
                    default_value: "",
                    is_key_field: ["id", "code", "ref", "default_code", "email", "vat"].includes(match.name),
                    lookup_strategy: "field_search",
                });
                count++;
            }
        }

        this.notification.add(`Auto-mapped ${count} fields.`, { type: "success" });
        setTimeout(() => this.updateSvgLines(), 50);
    }

    // ------------------------------------------------------------
    // SVG BEZIER CURVE RENDERER
    // ------------------------------------------------------------

    onCanvasMouseMove(e) {
        if (this.state.dragSourceCol && this.svgRef.el) {
            const rect = this.svgRef.el.getBoundingClientRect();
            this.state.dragMousePos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        }
    }

    onListScroll() {
        this.updateSvgLines();
    }

    updateSvgLines() {
        if (this.state.activeMode !== "mapping" || !this.svgRef.el || !this.containerRef.el) return;

        const svg = this.svgRef.el;
        const containerRect = this.containerRef.el.getBoundingClientRect();

        while (svg.firstChild) {
            svg.removeChild(svg.firstChild);
        }

        // Draw connections for all current mapping lines
        for (const m of this.state.mappings) {
            const targetEl = this.containerRef.el.querySelector(`[data-target-id="${m.target_field_id}"]`);
            if (!targetEl) continue;

            const targetRect = targetEl.getBoundingClientRect();
            const x2 = targetRect.left - containerRect.left;
            const y2 = targetRect.top + targetRect.height / 2 - containerRect.top;

            const x1 = containerRect.width * 0.35; // approx end of left panel
            const y1 = y2; // smooth alignment

            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            const dx = Math.abs(x2 - x1) * 0.5;
            const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

            path.setAttribute("d", d);
            path.setAttribute("fill", "none");
            path.setAttribute("stroke", m.is_key_field ? "#f0ad4e" : "#0d6efd");
            path.setAttribute("stroke-width", "2.5");
            path.setAttribute("stroke-dasharray", m.is_key_field ? "4 2" : "none");
            path.setAttribute("opacity", "0.85");

            svg.appendChild(path);
        }
    }

    // ------------------------------------------------------------
    // SAVE ALL DATA (TRANSFORMATIONS + MAPPINGS)
    // ------------------------------------------------------------

    async saveAll() {
        const id = this.resId;
        if (!id) return;

        this.state.isSaving = true;
        try {
            await this.orm.call("migration.template", "action_save_visual_mapping_data", [
                [id],
                this.state.transformations,
                this.state.mappings,
            ]);
            this.notification.add("Successfully saved all transformations and field mappings!", { type: "success" });
            await this.loadData();
        } catch (err) {
            console.error("Failed to save visual mapping data:", err);
            this.notification.add(`Error saving: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isSaving = false;
        }
    }
}

registry.category("view_widgets").add("visual_mapper", {
    component: VisualMapperWidget,
});
