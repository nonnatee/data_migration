/** @odoo-module **/

import { Component, useState, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MigrationPlanConsole extends Component {
    static template = "data_migration.MigrationPlanConsole";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            planId: this.props.action?.params?.plan_id || false,
            plan: null,
            stages: [],
            steps: [],
            recentRuns: [],
            logs: [],
            logFilter: "all", // 'all', 'error', 'warning', 'info'
            isLoading: true,
            isExecuting: false,
            autoRefresh: true,
        });

        this.pollInterval = null;

        onWillStart(async () => {
            await this.loadPlanData();
            this.startPolling();
        });

        onWillUnmount(() => {
            this.stopPolling();
        });
    }

    startPolling() {
        if (this.pollInterval) clearInterval(this.pollInterval);
        this.pollInterval = setInterval(async () => {
            if (this.state.autoRefresh && this.state.plan && (this.state.plan.state === "running" || this.state.isExecuting)) {
                await this.loadPlanData(false);
            }
        }, 3000);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async loadPlanData(showLoading = true) {
        if (showLoading) this.state.isLoading = true;

        try {
            // If no planId is passed, find the first active plan
            if (!this.state.planId) {
                const plans = await this.orm.searchRead("migration.plan", [], ["id", "name"], { limit: 1, order: "sequence asc, id desc" });
                if (plans.length > 0) {
                    this.state.planId = plans[0].id;
                } else {
                    this.state.isLoading = false;
                    return;
                }
            }

            // 1. Fetch Plan Details
            const [planData] = await this.orm.read("migration.plan", [this.state.planId], [
                "id", "name", "code", "state", "default_error_policy", "progress_percent",
                "stage_count", "step_count", "total_records", "processed_records",
                "success_records", "error_records", "stage_ids", "run_ids"
            ]);
            this.state.plan = planData;

            // 2. Fetch Stages
            const stages = await this.orm.searchRead(
                "migration.plan.stage",
                [["plan_id", "=", this.state.planId]],
                ["id", "name", "sequence", "state", "error_policy", "step_count", "total_records", "processed_records", "success_records", "error_records", "progress_percent", "step_ids"],
                { order: "sequence asc, id asc" }
            );
            this.state.stages = stages;

            // 3. Fetch Steps
            const stageIds = stages.map(s => s.id);
            const steps = await this.orm.searchRead(
                "migration.plan.step",
                [["stage_id", "in", stageIds]],
                ["id", "name", "stage_id", "sequence", "template_id", "target_model_name", "error_policy", "sample_limit", "state", "total_records", "processed_records", "success_records", "error_records", "progress_percent"],
                { order: "sequence asc, id asc" }
            );
            this.state.steps = steps;

            // 4. Fetch Recent Execution Runs
            const runs = await this.orm.searchRead(
                "migration.plan.run",
                [["plan_id", "=", this.state.planId]],
                ["id", "name", "state", "dry_run", "start_time", "end_time", "duration_seconds", "total_jobs", "total_records", "success_records", "error_records", "summary"],
                { limit: 5, order: "start_time desc, id desc" }
            );
            this.state.recentRuns = runs;

            // 5. Fetch Recent Audit Logs for Job Steps
            const templateIds = steps.map(s => s.template_id[0]).filter(Boolean);
            if (templateIds.length > 0) {
                const recentJobs = await this.orm.searchRead(
                    "migration.job",
                    [["template_id", "in", templateIds]],
                    ["id"],
                    { limit: 10, order: "id desc" }
                );
                const jobIds = recentJobs.map(j => j.id);
                if (jobIds.length > 0) {
                    const logs = await this.orm.searchRead(
                        "migration.log",
                        [["job_id", "in", jobIds]],
                        ["id", "job_id", "log_type", "message", "source_key", "target_record_id", "create_date", "error_traceback"],
                        { limit: 50, order: "id desc" }
                    );
                    this.state.logs = logs;
                } else {
                    this.state.logs = [];
                }
            }
        } catch (error) {
            console.error("Failed to load migration plan data:", error);
        } finally {
            if (showLoading) this.state.isLoading = false;
        }
    }

    getStepsForStage(stageId) {
        return this.state.steps.filter(s => s.stage_id[0] === stageId);
    }

    get filteredLogs() {
        if (this.state.logFilter === "all") return this.state.logs;
        return this.state.logs.filter(l => l.log_type === this.state.logFilter);
    }

    setLogFilter(filter) {
        this.state.logFilter = filter;
    }

    async runPreflightCheck() {
        if (!this.state.planId) return;
        try {
            const action = await this.orm.call("migration.plan", "action_preflight_check", [[this.state.planId]]);
            if (action) this.action.doAction(action);
        } catch (error) {
            this.notification.add(error.message || "Pre-flight check failed", { type: "danger" });
        }
    }

    openRunWizard() {
        if (!this.state.planId) return;
        this.action.doAction({
            name: "Execute Migration Plan",
            type: "ir.actions.act_window",
            res_model: "migration.plan.run.wizard",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_plan_id: this.state.planId,
                default_mode: "full_plan",
            },
        });
    }

    async executePlanDirect(dryRun = false) {
        if (!this.state.planId) return;
        this.state.isExecuting = true;
        try {
            await this.orm.call("migration.plan", "execute_plan", [[this.state.planId]], {
                dry_run: dryRun,
            });
            this.notification.add(dryRun ? "Dry-run simulation completed!" : "Migration plan executed successfully!", { type: "success" });
            await this.loadPlanData();
        } catch (error) {
            this.notification.add(error.message || "Execution encountered an error", { type: "danger" });
        } finally {
            this.state.isExecuting = false;
        }
    }

    async resetToDraft() {
        if (!this.state.planId) return;
        await this.orm.call("migration.plan", "action_reset_draft", [[this.state.planId]]);
        this.notification.add("Plan reset to Draft state.", { type: "info" });
        await this.loadPlanData();
    }

    openPlanForm() {
        if (!this.state.planId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "migration.plan",
            res_id: this.state.planId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openTemplateForm(templateId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "migration.template",
            res_id: templateId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    exportLogsCsv() {
        if (!this.state.logs.length) return;
        const headers = ["ID", "Timestamp", "Type", "Source Key", "Target ID", "Message"];
        const rows = this.state.logs.map(l => [
            l.id,
            `"${l.create_date || ''}"`,
            `"${l.log_type || ''}"`,
            `"${l.source_key || ''}"`,
            l.target_record_id || '',
            `"${(l.message || '').replace(/"/g, '""')}"`,
        ]);
        const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement("a");
        link.setAttribute("href", encodedUri);
        link.setAttribute("download", `migration_logs_plan_${this.state.plan?.code || 'export'}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
}

registry.category("actions").add("action_migration_plan_console", MigrationPlanConsole);
