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
            transformSearch: "",
            transformCategoryFilter: "",

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

    get filteredTransformations() {
        let transforms = this.state.transformations || [];
        if (this.state.transformCategoryFilter) {
            transforms = transforms.filter(t => t.transform_category === this.state.transformCategoryFilter);
        }
        if (this.state.transformSearch) {
            const q = this.state.transformSearch.toLowerCase();
            transforms = transforms.filter(t =>
                (t.source_field && t.source_field.toLowerCase().includes(q)) ||
                (t.output_field && t.output_field.toLowerCase().includes(q)) ||
                (t.transform_category && t.transform_category.toLowerCase().includes(q)) ||
                (t.cleansing_type && t.cleansing_type.toLowerCase().includes(q))
            );
        }
        return transforms;
    }

    getTransformHint(t) {
        if (!t) return "Cleanses and transforms input variable.";
        const cat = t.transform_category || "cleansing";
        if (cat === "cleansing") {
            const hints = {
                trim: '"John Doe   " ➔ "John Doe" (Removes leading & trailing whitespace)',
                upper: '"acme corp" ➔ "ACME CORP" (Converts all characters to uppercase)',
                lower: '"User@Company.COM" ➔ "user@company.com" (Standardizes email/text to lowercase)',
                title: '"john doe jr" ➔ "John Doe Jr" (Capitalizes first letter of each word)',
                capitalize: '"pending review" ➔ "Pending review" (Capitalizes first letter only)',
                pad_left: '"42" (pad="0", len=6) ➔ "000042" (Fixed-width invoice / customer codes)',
                pad_right: '"SKU" (pad="_", len=8) ➔ "SKU_____" (Appends padding to target length)',
                regex: 'Pattern: r"[^\\d+]" Repl: "" ➔ "(555) 123-4567" becomes "5551234567"',
                regex_extract: 'Pattern: r"INV-(\\d+)" Group: 1 ➔ Extracts "1002" from "INV-1002-2026"',
                strip_html: '"<p><b>Hello</b> World</p>" ➔ "Hello World" (Strips HTML tags & decodes entities)',
                strip_non_numeric: '"$1,250.75 USD" ➔ "1250.75" (Keeps only digits and decimal point)',
                strip_non_alphanumeric: '"AB#12-34_XY!" ➔ "AB1234XY" (Strips punctuation & symbols)',
                handle_null: 'Empty or None ➔ Default fallback value (e.g. "N/A" or "0")',
                drop_if_null: 'Empty or None ➔ Drops / skips entire record from ETL load',
            };
            return hints[t.cleansing_type] || "Data cleansing and sanitization.";
        } else if (cat === "filter_row") {
            if (t.filter_action === "keep_if") {
                return 'Keep record ONLY if condition matches (e.g. status == "active" or amount > 0); drop otherwise.';
            } else {
                return 'Drop / skip record if condition matches (e.g. is_deleted == "1" or country == "TEST"); keep otherwise.';
            }
        } else if (cat === "date_format") {
            return '"25/12/2025" (Input: "%d/%m/%Y", Output: "%Y-%m-%d") ➔ "2025-12-25". Supports tz offset & day offsets.';
        } else if (cat === "unit_conversion") {
            if (t.unit_type === "mass") return `Mass conversion (${t.source_unit || "lb"} ➔ ${t.target_unit || "kg"}): e.g. 100 lb ➔ ~45.36 kg`;
            if (t.unit_type === "length") return `Length conversion (${t.source_unit || "in"} ➔ ${t.target_unit || "cm"}): e.g. 10 in ➔ 25.4 cm`;
            if (t.unit_type === "volume") return `Volume conversion (${t.source_unit || "gal"} ➔ ${t.target_unit || "l"}): e.g. 5 gal ➔ ~18.93 l`;
            if (t.unit_type === "temp") return `Temperature conversion (${t.source_unit || "F"} ➔ ${t.target_unit || "C"}): e.g. 98.6 °F ➔ 37.0 °C`;
            return "Multiplier ratio: Value * Scale Ratio (e.g. 100 * 1.07 = 107.0 for VAT/markup)";
        } else if (cat === "type_conversion") {
            const hints = {
                string: '123 ➔ "123" (Casts number/object to text string)',
                integer: '"123.45" ➔ 123 (Casts to integer whole number)',
                float: '"$1250.50" ➔ 1250.50 (Casts to floating point decimal)',
                boolean: '"yes", "1", "true", "active" ➔ True; others ➔ False',
                date: '"2026-08-29 15:30:00" ➔ "2026-08-29" (Extracts ISO date portion)',
                datetime: '"2026-08-29" ➔ "2026-08-29 00:00:00" (Expands date to timestamp)',
                json_parse: '\'{"key": "val"}\' ➔ Python dictionary object',
                json_dump: 'Dictionary / List ➔ JSON string representation',
                base64_encode: '"hello" ➔ "aGVsbG8=" (Encodes text/binary for attachments)',
                base64_decode: '"aGVsbG8=" ➔ "hello" (Decodes base64 string back to text)',
            };
            return hints[t.target_type] || "Casts variable to target data type.";
        } else if (cat === "value_map") {
            return 'JSON: {"M": "Male", "F": "Female", "O": "Other"} ➔ Translates legacy codes to standard values.';
        } else if (cat === "math_expr") {
            const hints = {
                add: "value + operand (e.g. 100 + 15 = 115)",
                subtract: "value - operand (e.g. 100 - 20 = 80)",
                multiply: "value * operand (e.g. qty * unit_price)",
                divide: "value / operand (e.g. total / 12 = monthly_installment)",
                round: "round(value, precision) (e.g. 12.3456 with precision 2 ➔ 12.35)",
                modulo: "value % operand (e.g. 10 % 3 = 1)",
                percentage: "(value / 100.0) * operand (e.g. 10% discount on 250 = 25.0)",
                abs: "abs(value) (e.g. -45.5 ➔ 45.5)",
            };
            return hints[t.math_op] || "Applies arithmetic calculation to variable.";
        } else if (cat === "string_slice") {
            const hints = {
                slice: 'Start 0, End 4 on "2026-Q1" ➔ "2026" (Character index substring)',
                left: 'Length 3 on "DE12345" ➔ "DE" (First N characters from left)',
                right: 'Length 4 on "ABC1234" ➔ "1234" (Last N characters from right)',
                split: 'Delimiter "-" Index 1 on "INV-2026-001" ➔ "2026" (Token split)',
            };
            return hints[t.slice_mode] || "Extracts substring or splits variable.";
        } else if (cat === "slugify") {
            return '"Apple iPhone 15 Pro (128GB)!" ➔ "apple_iphone_15_pro_128gb" (URL/XML-ID safe slug)';
        } else if (cat === "case_when") {
            return 'JSON: [{"when": "VIP", "then": 0.20}, {"when": "STD", "then": 0.05}] ➔ Multi-branch logic';
        } else if (cat === "python_expr") {
            return 'value.strip().lower() if value else default or record.get("qty", 0) * record.get("price", 0)';
        } else if (cat === "ai_prompt") {
            return '"Extract province from Thai address: {value}" or "Categorize product into category: {value}"';
        }
        return "Cleanses and transforms input variable.";
    }

    loadExampleToSandbox(t) {
        if (!t) return;
        const cat = t.transform_category || "cleansing";
        if (cat === "cleansing") {
            if (t.cleansing_type === "trim") this.state.sampleInput = "   Sample Text Value   ";
            else if (t.cleansing_type === "upper" || t.cleansing_type === "title") this.state.sampleInput = "john doe jr";
            else if (t.cleansing_type === "lower") this.state.sampleInput = "John.Doe@ACME.COM";
            else if (t.cleansing_type === "pad_left") this.state.sampleInput = "42";
            else if (t.cleansing_type === "regex") this.state.sampleInput = "(+66) 81-234-5678";
            else if (t.cleansing_type === "regex_extract") this.state.sampleInput = "INV-2026-098";
            else if (t.cleansing_type === "strip_html") this.state.sampleInput = "<p>Hello <b>World</b></p>";
            else if (t.cleansing_type === "strip_non_numeric") this.state.sampleInput = "$1,450.50 USD";
            else this.state.sampleInput = "Sample Value";
        } else if (cat === "date_format") {
            this.state.sampleInput = "25/12/2025";
        } else if (cat === "unit_conversion") {
            this.state.sampleInput = "100";
        } else if (cat === "math_expr") {
            this.state.sampleInput = "100";
        } else if (cat === "string_slice") {
            this.state.sampleInput = "INV-2026-001";
        } else if (cat === "slugify") {
            this.state.sampleInput = "Apple iPhone 15 Pro (128GB)!";
        } else if (cat === "filter_row") {
            this.state.sampleInput = "active";
        } else {
            this.state.sampleInput = "123.45";
        }
        this.notification.add("Loaded sample input for " + cat, { type: "info" });
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
            apply_filter: false,
            filter_field: src,
            filter_operator: "=",
            filter_value: "",
            filter_action: "keep_if",
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
            apply_filter: false,
            filter_field: col,
            filter_operator: "=",
            filter_value: "",
            filter_action: "keep_if",
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
                "sequence", "transform_category", "cleansing_type", "regex_pattern", "regex_replace",
                "unit_type", "source_unit", "target_unit", "apply_filter", "filter_field", "filter_operator", "filter_value", "filter_action"
            ]);

            const src = this.state.selectedSourceCol || (this.state.rawColumns[0] || "col1");
            for (const s of steps) {
                this.state.transformations.push({
                    sequence: (this.state.transformations.length + 1) * 10,
                    source_field: src,
                    output_field: src,
                    apply_filter: !!s.apply_filter,
                    filter_field: s.filter_field || src,
                    filter_operator: s.filter_operator || "=",
                    filter_value: s.filter_value || "",
                    filter_action: s.filter_action || "keep_if",
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
        if (t.transform_category === "filter_row") {
            const s = String(val).trim();
            const target = String(t.filter_value || "").trim();
            let matched = false;
            if (t.filter_operator === "=") matched = s.toLowerCase() === target.toLowerCase();
            else if (t.filter_operator === "!=") matched = s.toLowerCase() !== target.toLowerCase();
            else if (t.filter_operator === "contains") matched = s.toLowerCase().includes(target.toLowerCase());
            else if (t.filter_operator === "is_null") matched = s === "";
            else if (t.filter_operator === "is_not_null") matched = s !== "";
            else matched = true;

            if (t.filter_action === "keep_if" && !matched) return "[SKIPPED / FILTERED OUT]";
            if (t.filter_action === "drop_if" && matched) return "[SKIPPED / FILTERED OUT]";
            return val;
        }

        if (t.transform_category === "cleansing") {
            const s = String(val);
            if (t.cleansing_type === "trim") return s.trim();
            if (t.cleansing_type === "upper") return s.toUpperCase();
            if (t.cleansing_type === "lower") return s.toLowerCase();
            if (t.cleansing_type === "title") return s.replace(/\b\w/g, c => c.toUpperCase());
            if (t.cleansing_type === "capitalize") return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
            if (t.cleansing_type === "pad_left") return s.padStart(t.pad_count || 10, t.pad_char || "0");
            if (t.cleansing_type === "pad_right") return s.padEnd(t.pad_count || 10, t.pad_char || "0");
            if (t.cleansing_type === "regex" && t.regex_pattern) {
                return s.replace(new RegExp(t.regex_pattern, "g"), t.regex_replace || "");
            }
            if (t.cleansing_type === "strip_html") return s.replace(/<[^>]*>?/gm, "");
            if (t.cleansing_type === "strip_non_numeric") return s.replace(/[^\d.]/g, "");
            if (t.cleansing_type === "strip_non_alphanumeric") return s.replace(/[^a-zA-Z0-9]/g, "");
            return s.trim();
        } else if (t.transform_category === "unit_conversion") {
            const n = parseFloat(val) || 0;
            if (t.unit_type === "mass" && t.source_unit === "lb" && t.target_unit === "kg") return Math.round(n * 0.453592 * 1000) / 1000;
            if (t.unit_type === "mass" && t.source_unit === "kg" && t.target_unit === "lb") return Math.round(n * 2.20462 * 1000) / 1000;
            if (t.unit_type === "length" && t.source_unit === "in" && t.target_unit === "cm") return Math.round(n * 2.54 * 100) / 100;
            if (t.unit_type === "temp" && t.source_unit === "F" && t.target_unit === "C") return Math.round(((n - 32) * 5 / 9) * 10) / 10;
            return n * (parseFloat(t.custom_scale_ratio) || 1.0);
        } else if (t.transform_category === "math_expr") {
            const n = parseFloat(val) || 0;
            const op = parseFloat(t.math_operand) || 0;
            if (t.math_op === "add") return n + op;
            if (t.math_op === "subtract") return n - op;
            if (t.math_op === "multiply") return n * op;
            if (t.math_op === "divide" && op !== 0) return n / op;
            if (t.math_op === "round") return Math.round(n * 100) / 100;
            if (t.math_op === "percentage") return (n / 100.0) * op;
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
        const targetListEl = this.containerRef.el.querySelector('[t-ref="targetList"]') || this.containerRef.el.querySelector('.o_mapper_target_panel .o_mapper_scroll_pane');
        const targetListRect = targetListEl ? targetListEl.getBoundingClientRect() : containerRect;

        while (svg.firstChild) {
            svg.removeChild(svg.firstChild);
        }

        // Draw connections for all current mapping lines
        for (const m of this.state.mappings) {
            const targetEl = this.containerRef.el.querySelector(`[data-target-id="${m.target_field_id}"]`);
            if (!targetEl) continue;

            const targetRect = targetEl.getBoundingClientRect();
            // Skip lines for target cards that are scrolled outside the visible scroll pane
            if (targetRect.bottom < targetListRect.top || targetRect.top > targetListRect.bottom) {
                continue;
            }

            const x2 = targetRect.left - containerRect.left;
            const y2 = targetRect.top + targetRect.height / 2 - containerRect.top;

            let x1 = containerRect.width * 0.38;
            let y1 = y2;

            // Connect directly to source pill if visible in source list
            const sourceEl = this.containerRef.el.querySelector(`[data-source-var="${m.source_field}"]`);
            if (sourceEl) {
                const sourceListEl = this.containerRef.el.querySelector('[t-ref="sourceList"]') || this.containerRef.el.querySelector('.o_mapper_source_panel .o_mapper_scroll_pane');
                const sourceListRect = sourceListEl ? sourceListEl.getBoundingClientRect() : containerRect;
                const sourceRect = sourceEl.getBoundingClientRect();
                if (sourceRect.bottom >= sourceListRect.top && sourceRect.top <= sourceListRect.bottom) {
                    x1 = sourceRect.right - containerRect.left;
                    y1 = sourceRect.top + sourceRect.height / 2 - containerRect.top;
                }
            }

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
