/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class VisualMapperWidget extends Component {
    static template = "data_migration.VisualMapperWidget";
    static props = {
        record: { type: Object, optional: true },
        resId: { type: Number, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.svgRef = useRef("svgCanvas");
        this.containerRef = useRef("mapperContainer");

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
            
            // Search filters
            sourceSearch: "",
            targetSearch: "",
            
            // Selected state
            selectedSourceCol: null,
            selectedLineIndex: null,

            // Live preview
            sampleInput: " 150.50 lbs ",
            sampleResult: null,
            isTestingSample: false,

            // New step drafting
            newStepCategory: "cleansing",
        });

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            this.updateSvgLines();
            window.addEventListener("resize", this.onResizeBound);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this.onResizeBound);
        });

        this.onResizeBound = () => this.updateSvgLines();
    }

    get resId() {
        if (this.props.record && this.props.record.resId) {
            return this.props.record.resId;
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

    get filteredSourceColumns() {
        if (!this.state.sourceSearch) return this.state.sourceColumns;
        const q = this.state.sourceSearch.toLowerCase();
        return this.state.sourceColumns.filter(c => c.toLowerCase().includes(q));
    }

    get filteredTargetFields() {
        if (!this.state.targetSearch) return this.state.targetFields;
        const q = this.state.targetSearch.toLowerCase();
        return this.state.targetFields.filter(f => 
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
                // Update existing line target
                this.state.mappingLines[lineIdx].target_field_id = targetField.id;
                this.state.mappingLines[lineIdx].target_field_name = targetField.name;
                this.state.mappingLines[lineIdx].target_field_ttype = targetField.ttype;
            } else {
                // Create new line
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

    getCategoryLabel(cat) {
        const map = {
            cleansing: "Data Cleansing",
            date_format: "Date & Time Formatting",
            unit_conversion: "Unit Conversion",
            type_conversion: "Data Type Conversion",
            value_map: "Value Mapping Table",
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
            // If line is persistent (integer ID), call backend action_test_pipeline
            if (typeof line.id === "number") {
                const res = await this.orm.call("migration.mapping.line", "action_test_pipeline", [line.id, this.state.sampleInput]);
                this.state.sampleResult = res;
            } else {
                // Client-side simulation
                let currentVal = this.state.sampleInput;
                const traces = [];
                (line.transforms || []).forEach((t, idx) => {
                    const prev = currentVal;
                    if (t.transform_category === "cleansing") {
                        if (t.cleansing_type === "trim") currentVal = String(currentVal).trim();
                        else if (t.cleansing_type === "upper") currentVal = String(currentVal).toUpperCase();
                        else if (t.cleansing_type === "lower") currentVal = String(currentVal).toLowerCase();
                        else if (t.cleansing_type === "capitalize") currentVal = String(currentVal).charAt(0).toUpperCase() + String(currentVal).slice(1);
                    }
                    traces.append ? traces.append({ step: idx + 1, name: t.name, input: prev, output: currentVal, status: "ok" }) : traces.push({ step: idx + 1, name: t.name || `Step ${idx + 1}`, input: prev, output: currentVal, status: "ok" });
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

    updateSvgLines() {
        if (!this.svgRef.el || !this.containerRef.el) return;
        const containerRect = this.containerRef.el.getBoundingClientRect();
        const svgEl = this.svgRef.el;
        svgEl.setAttribute("width", containerRect.width);
        svgEl.setAttribute("height", containerRect.height);

        // Clear existing paths
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
                path.setAttribute("style", "cursor: pointer; transition: all 0.2s ease;");
                path.addEventListener("click", () => this.selectLine(idx));

                svgEl.appendChild(path);
            }
        });
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

registry.category("actions").add("data_migration.visual_mapper", VisualMapperWidget);
