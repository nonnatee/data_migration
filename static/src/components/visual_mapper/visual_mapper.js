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
            templateId: null,
            templateName: "",
            connectionName: "",
            targetModelName: "",
            sourceColumns: [],
            targetFields: [],
            mappingLines: [],
            transformPresets: [],
            
            // Filters
            sourceSearch: "",
            targetSearch: "",
            filterMode: "all", // 'all', 'mapped', 'unmapped'
            
            // Selected state
            selectedSourceCol: null,
            selectedLineIndex: null,
            selectedPresetId: "",

            // Drag and Drop state
            isDraggingLink: false,
            dragSourceCol: null,
            dragOverTargetId: null,
            dragMousePos: { x: 0, y: 0 },

            // Live preview
            sampleInput: " 150.50 lbs ",
            sampleResult: null,
            isTestingSample: false,

            // New step drafting
            newStepCategory: "cleansing",
            
            // Scroll optimization state
            isScrolling: false,
        });

        this.scrollTimeout = null;

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            this.updateSvgLines();
            window.addEventListener("resize", this.onResizeBound);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this.onResizeBound);
            if (this.scrollTimeout) clearTimeout(this.scrollTimeout);
        });

        this.onResizeBound = () => this.updateSvgLines();
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
            this.state.sourceColumns = data.source_columns || [];
            this.state.targetFields = data.target_fields || [];
            this.state.mappingLines = data.mapping_lines || [];
            this.state.transformPresets = data.transform_presets || [];

            if (this.state.mappingLines.length > 0) {
                this.state.selectedLineIndex = 0;
                this.state.selectedSourceCol = this.state.mappingLines[0].source_field;
            }
        } catch (err) {
            console.error("Failed to load visual mapping data:", err);
            this.notification.add(`Error loading data: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isLoading = false;
            setTimeout(() => this.updateSvgLines(), 100);
        }
    }

    get mappedSourceCount() {
        return this.state.sourceColumns.filter(c => this.isSourceMapped(c)).length;
    }

    get unmappedSourceCount() {
        return this.state.sourceColumns.length - this.mappedSourceCount;
    }

    get filteredSourceColumns() {
        let cols = this.state.sourceColumns;
        if (this.state.filterMode === "mapped") {
            cols = cols.filter(c => this.isSourceMapped(c));
        } else if (this.state.filterMode === "unmapped") {
            cols = cols.filter(c => !this.isSourceMapped(c));
        }

        if (!this.state.sourceSearch) return cols;
        const q = this.state.sourceSearch.toLowerCase();
        return cols.filter(c => c.toLowerCase().includes(q));
    }

    get filteredTargetFields() {
        let fields = this.state.targetFields;
        if (this.state.filterMode === "mapped") {
            fields = fields.filter(f => this.isTargetMapped(f.id));
        } else if (this.state.filterMode === "unmapped") {
            fields = fields.filter(f => !this.isTargetMapped(f.id));
        }

        if (!this.state.targetSearch) return fields;
        const q = this.state.targetSearch.toLowerCase();
        return fields.filter(f => 
            f.name.toLowerCase().includes(q) || 
            (f.field_description && f.field_description.toLowerCase().includes(q))
        );
    }

    get activeLine() {
        if (this.state.selectedLineIndex !== null && this.state.selectedLineIndex >= 0 && this.state.selectedLineIndex < this.state.mappingLines.length) {
            return this.state.mappingLines[this.state.selectedLineIndex];
        }
        return null;
    }

    setFilterMode(mode) {
        this.state.filterMode = mode;
        setTimeout(() => this.updateSvgLines(), 50);
    }

    // --- Drag and Drop Handlers ---

    onSourceDragStart(event, col) {
        this.state.isDraggingLink = true;
        this.state.dragSourceCol = col;
        this.selectSource(col);

        if (event.dataTransfer) {
            event.dataTransfer.effectAllowed = "link";
            event.dataTransfer.setData("text/plain", col);
        }
    }

    onCanvasMouseMove(event) {
        if (!this.state.isDraggingLink || !this.containerRef.el) return;
        const containerRect = this.containerRef.el.getBoundingClientRect();
        this.state.dragMousePos = {
            x: event.clientX - containerRect.left,
            y: event.clientY - containerRect.top,
        };
        this.updateSvgLines();
    }

    onTargetDragOver(event, targetField) {
        if (!this.state.isDraggingLink) return;
        event.preventDefault();
        if (event.dataTransfer) {
            event.dataTransfer.dropEffect = "link";
        }
        this.state.dragOverTargetId = targetField.id;
    }

    onTargetDrop(event, targetField) {
        if (!this.state.isDraggingLink || !this.state.dragSourceCol) return;
        event.preventDefault();
        
        const sourceCol = this.state.dragSourceCol;
        this.selectSource(sourceCol);
        this.selectTarget(targetField);

        this.onDragEnd();
    }

    onDragEnd() {
        this.state.isDraggingLink = false;
        this.state.dragSourceCol = null;
        this.state.dragOverTargetId = null;
        this.updateSvgLines();
    }

    // --- Scroll Optimization ---

    onListScroll() {
        this.state.isScrolling = true;
        if (this.svgRef.el) {
            this.svgRef.el.style.opacity = "0.3";
        }

        if (this.scrollTimeout) clearTimeout(this.scrollTimeout);
        this.scrollTimeout = setTimeout(() => {
            this.state.isScrolling = false;
            if (this.svgRef.el) {
                this.svgRef.el.style.opacity = "1";
            }
            this.updateSvgLines();
        }, 120);
    }

    // --- Batch Toolbar Actions ---

    autoMapMatching() {
        if (!this.state.sourceColumns || !this.state.targetFields) return;
        
        const fieldMap = {};
        const fieldLabelMap = {};
        this.state.targetFields.forEach(f => {
            fieldMap[f.name.toLowerCase()] = f;
            if (f.field_description) {
                fieldLabelMap[f.field_description.toLowerCase()] = f;
            }
        });

        let createdCount = 0;
        this.state.sourceColumns.forEach(col => {
            if (this.isSourceMapped(col)) return;

            const colClean = col.strip ? col.strip().toLowerCase().replace(/ /g, '_').replace(/-/g, '_') : col.toLowerCase().replace(/ /g, '_');
            const matchField = fieldMap[colClean] || fieldLabelMap[col.toLowerCase()];

            if (matchField) {
                this.state.mappingLines.push({
                    id: `temp_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
                    source_field: col,
                    target_field_id: matchField.id,
                    target_field_name: matchField.name,
                    target_field_ttype: matchField.ttype,
                    is_key_field: ["id", "code", "ref", "email", "vat"].includes(matchField.name),
                    transform_type: "direct",
                    default_value: "",
                    lookup_strategy: "field_search",
                    transforms: [
                        {
                            id: `temp_t_${Date.now()}`,
                            sequence: 10,
                            transform_category: "cleansing",
                            cleansing_type: "trim",
                            name: "Cleanse: Trim Whitespace",
                        }
                    ]
                });
                createdCount++;
            }
        });

        if (createdCount > 0) {
            this.notification.add(`Auto-mapped ${createdCount} matching fields!`, { type: "success" });
            this.updateSvgLines();
        } else {
            this.notification.add("No additional matching field names found.", { type: "info" });
        }
    }

    clearAllMappings() {
        if (confirm("Are you sure you want to clear all current field mapping links?")) {
            this.state.mappingLines = [];
            this.state.selectedLineIndex = null;
            this.state.selectedSourceCol = null;
            this.updateSvgLines();
            this.notification.add("All field mappings cleared.", { type: "warning" });
        }
    }

    // --- Line & Selection Management ---

    selectSource(col) {
        this.state.selectedSourceCol = col;
        const existingIdx = this.state.mappingLines.findIndex(l => l.source_field === col);
        if (existingIdx !== -1) {
            this.state.selectedLineIndex = existingIdx;
        } else {
            this.state.selectedLineIndex = null;
        }
        this.updateSvgLines();
    }

    selectTarget(targetField) {
        if (this.state.selectedSourceCol) {
            let lineIdx = this.state.mappingLines.findIndex(l => l.source_field === this.state.selectedSourceCol);
            if (lineIdx !== -1) {
                this.state.mappingLines[lineIdx].target_field_id = targetField.id;
                this.state.mappingLines[lineIdx].target_field_name = targetField.name;
                this.state.mappingLines[lineIdx].target_field_ttype = targetField.ttype;
            } else {
                const newLine = {
                    id: `temp_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
                    source_field: this.state.selectedSourceCol,
                    target_field_id: targetField.id,
                    target_field_name: targetField.name,
                    target_field_ttype: targetField.ttype,
                    is_key_field: ["id", "code", "ref", "email", "vat"].includes(targetField.name),
                    transform_type: "direct",
                    default_value: "",
                    lookup_strategy: "field_search",
                    transforms: [
                        {
                            id: `temp_t_${Date.now()}`,
                            sequence: 10,
                            transform_category: "cleansing",
                            cleansing_type: "trim",
                            name: "Cleanse: Trim Whitespace",
                        }
                    ]
                };
                this.state.mappingLines.push(newLine);
                lineIdx = this.state.mappingLines.length - 1;
            }
            this.state.selectedLineIndex = lineIdx;
            this.updateSvgLines();
        }
    }

    selectLine(idx) {
        this.state.selectedLineIndex = idx;
        const line = this.state.mappingLines[idx];
        if (line) {
            this.state.selectedSourceCol = line.source_field;
        }
        this.updateSvgLines();
    }

    deleteLine(idx) {
        this.state.mappingLines.splice(idx, 1);
        if (this.state.selectedLineIndex === idx) {
            this.state.selectedLineIndex = this.state.mappingLines.length > 0 ? 0 : null;
            if (this.state.selectedLineIndex !== null) {
                this.state.selectedSourceCol = this.state.mappingLines[0].source_field;
            } else {
                this.state.selectedSourceCol = null;
            }
        }
        this.updateSvgLines();
    }

    addTransformStep() {
        const line = this.activeLine;
        if (!line) return;
        if (!line.transforms) line.transforms = [];

        const cat = this.state.newStepCategory;
        const newStep = {
            id: `temp_t_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
            sequence: (line.transforms.length + 1) * 10,
            transform_category: cat,
            cleansing_type: "trim",
            pad_char: "0",
            pad_count: 10,
            regex_pattern: "",
            regex_replace: "",
            input_date_format: "%Y-%m-%d",
            output_date_format: "%Y-%m-%d",
            tz_offset_hours: 0.0,
            unit_type: "mass",
            source_unit: "kg",
            target_unit: "lb",
            custom_scale_ratio: 1.0,
            target_type: "string",
            value_mapping_json: '{"source_val": "target_val"}',
            python_code: 'value.strip().title() if value else default',
            default_fallback: "",
            math_op: "add",
            math_operand: 0.0,
            math_round_precision: 2,
            slice_mode: "slice",
            slice_start: 0,
            slice_end: 10,
            slice_length: 5,
            split_delimiter: ",",
            split_index: 0,
            case_when_json: "[]",
            ai_prompt_template: "Extract and normalize from: {value}",
            name: this.getCategoryLabel(cat),
        };
        line.transforms.push(newStep);
    }

    removeTransformStep(stepIdx) {
        const line = this.activeLine;
        if (line && line.transforms) {
            line.transforms.splice(stepIdx, 1);
        }
    }

    async applySelectedPreset() {
        const line = this.activeLine;
        const presetId = Number(this.state.selectedPresetId);
        if (!line || !presetId) return;

        try {
            if (typeof line.id === "number") {
                await this.orm.call("migration.mapping.line", "action_apply_preset", [line.id, presetId]);
                this.notification.add("Preset applied to field mapping successfully!", { type: "success" });
                await this.loadData();
            } else {
                this.notification.add("Please save visual mappings first before applying backend presets.", { type: "warning" });
            }
        } catch (err) {
            console.error("Failed to apply preset:", err);
            this.notification.add(`Apply preset failed: ${err.message || err}`, { type: "danger" });
        }
    }

    async saveAsPreset() {
        const line = this.activeLine;
        if (!line || !line.transforms || line.transforms.length === 0) {
            this.notification.add("Active line has no transformation steps to save as preset.", { type: "warning" });
            return;
        }

        const presetName = prompt("Enter a name for this Transformation Preset Template:", `${line.source_field} -> ${line.target_field_name} Preset`);
        if (!presetName) return;

        try {
            if (typeof line.id === "number") {
                await this.orm.call("migration.mapping.line", "action_save_as_preset", [line.id, presetName]);
                this.notification.add(`Preset '${presetName}' saved successfully!`, { type: "success" });
                await this.loadData();
            } else {
                this.notification.add("Please save visual mappings first before exporting as preset template.", { type: "warning" });
            }
        } catch (err) {
            console.error("Failed to save preset:", err);
            this.notification.add(`Save preset failed: ${err.message || err}`, { type: "danger" });
        }
    }

    getCategoryLabel(cat) {
        const map = {
            cleansing: "Data Cleansing",
            date_format: "Date & Time Formatting",
            unit_conversion: "Unit Conversion",
            type_conversion: "Data Type Conversion",
            value_map: "Value Mapping Table",
            math_expr: "Math & Arithmetic",
            string_slice: "String Substring / Split",
            slugify: "URL / Code Slugify",
            case_when: "Case-When Branching",
            ai_prompt: "AI Prompt Transformer",
            python_expr: "Python Expression",
        };
        return map[cat] || cat;
    }

    async testLiveSample() {
        const line = this.activeLine;
        if (!line) return;
        this.state.isTestingSample = true;
        this.state.sampleResult = null;

        try {
            if (typeof line.id === "number") {
                const res = await this.orm.call("migration.mapping.line", "action_test_pipeline", [line.id, this.state.sampleInput]);
                this.state.sampleResult = res;
            } else {
                let currentVal = this.state.sampleInput;
                const traces = [];
                (line.transforms || []).forEach((t, idx) => {
                    const prev = currentVal;
                    if (t.transform_category === "cleansing") {
                        if (t.cleansing_type === "trim") currentVal = String(currentVal).trim();
                        else if (t.cleansing_type === "upper") currentVal = String(currentVal).toUpperCase();
                        else if (t.cleansing_type === "lower") currentVal = String(currentVal).toLowerCase();
                        else if (t.cleansing_type === "capitalize") currentVal = String(currentVal).charAt(0).toUpperCase() + String(currentVal).slice(1);
                    } else if (t.transform_category === "math_expr") {
                        const num = parseFloat(currentVal) || 0;
                        if (t.math_op === "add") currentVal = num + (t.math_operand || 0);
                        else if (t.math_op === "multiply") currentVal = num * (t.math_operand || 1);
                        else if (t.math_op === "round") currentVal = Number(num.toFixed(t.math_round_precision || 2));
                    } else if (t.transform_category === "slugify") {
                        currentVal = String(currentVal).trim().toLowerCase().replace(/[^\w\s-]/g, '').replace(/[-\s]+/g, '_');
                    }
                    traces.push({ step: idx + 1, name: t.name || `Step ${idx + 1}`, input: prev, output: currentVal, status: "ok" });
                });
                this.state.sampleResult = { input: this.state.sampleInput, final_output: currentVal, traces };
            }
        } catch (err) {
            console.error("Live test failed:", err);
            this.notification.add(`Test failed: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isTestingSample = false;
        }
    }

    async saveMappings() {
        if (!this.state.templateId) return;
        this.state.isSaving = true;
        try {
            await this.orm.call("migration.template", "action_save_visual_mapping", [this.state.templateId, this.state.mappingLines]);
            this.notification.add("Visual field mapping and transformation rules saved successfully!", { type: "success" });
            await this.loadData();
        } catch (err) {
            console.error("Failed to save visual mapping:", err);
            this.notification.add(`Save failed: ${err.message || err}`, { type: "danger" });
        } finally {
            this.state.isSaving = false;
        }
    }

    // --- SVG Canvas Curve Rendering ---

    updateSvgLines() {
        if (!this.svgRef.el || !this.containerRef.el) return;
        const containerRect = this.containerRef.el.getBoundingClientRect();
        const svgEl = this.svgRef.el;
        svgEl.setAttribute("width", containerRect.width);
        svgEl.setAttribute("height", containerRect.height);

        while (svgEl.firstChild) {
            svgEl.removeChild(svgEl.firstChild);
        }

        const lines = this.state.mappingLines;
        lines.forEach((line, idx) => {
            const sPort = this.containerRef.el.querySelector(`[data-source-port="${line.source_field}"]`);
            const tPort = this.containerRef.el.querySelector(`[data-target-port="${line.target_field_id}"]`);

            if (sPort && tPort) {
                const sRect = sPort.getBoundingClientRect();
                const tRect = tPort.getBoundingClientRect();

                const x1 = sRect.right - containerRect.left;
                const y1 = sRect.top + sRect.height / 2 - containerRect.top;
                const x2 = tRect.left - containerRect.left;
                const y2 = tRect.top + tRect.height / 2 - containerRect.top;

                const dx = Math.abs(x2 - x1) * 0.5;
                const pathD = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

                const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                path.setAttribute("d", pathD);
                path.setAttribute("fill", "none");
                
                const isSelected = this.state.selectedLineIndex === idx;
                path.setAttribute("stroke", isSelected ? "#00a09d" : "#7c7bad");
                path.setAttribute("stroke-width", isSelected ? "3.5" : "2");
                if (isSelected) {
                    path.setAttribute("stroke-dasharray", "5,5");
                }
                path.setAttribute("style", "cursor: pointer; transition: stroke 0.2s, stroke-width 0.2s;");
                path.addEventListener("click", () => this.selectLine(idx));

                svgEl.appendChild(path);
            }
        });

        // Draw live rubberband drag line if user is dragging from a source port
        if (this.state.isDraggingLink && this.state.dragSourceCol) {
            const sPort = this.containerRef.el.querySelector(`[data-source-port="${this.state.dragSourceCol}"]`);
            if (sPort) {
                const sRect = sPort.getBoundingClientRect();
                const x1 = sRect.right - containerRect.left;
                const y1 = sRect.top + sRect.height / 2 - containerRect.top;

                const x2 = this.state.dragMousePos.x || (x1 + 100);
                const y2 = this.state.dragMousePos.y || y1;

                const dx = Math.abs(x2 - x1) * 0.5;
                const pathD = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

                const dragPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
                dragPath.setAttribute("d", pathD);
                dragPath.setAttribute("fill", "none");
                dragPath.setAttribute("stroke", "#ff9800");
                dragPath.setAttribute("stroke-width", "3");
                dragPath.setAttribute("stroke-dasharray", "6,4");
                dragPath.setAttribute("class", "o_rubberband_path");
                svgEl.appendChild(dragPath);
            }
        }
    }

    isSourceMapped(col) {
        return this.state.mappingLines.some(l => l.source_field === col);
    }

    isTargetMapped(targetId) {
        return this.state.mappingLines.some(l => l.target_field_id === targetId);
    }
}

registry.category("fields").add("visual_mapper", {
    component: VisualMapperWidget,
});

registry.category("view_widgets").add("visual_mapper", {
    component: VisualMapperWidget,
});

registry.category("actions").add("data_migration.visual_mapper", VisualMapperWidget);
