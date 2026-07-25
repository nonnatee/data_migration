/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MigrationStudioDashboard extends Component {
    static template = "data_migration.MigrationStudioDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            stats: {
                totalJobs: 0,
                successCount: 0,
                errorCount: 0,
                activeConnections: 0,
                totalTemplates: 0,
                totalMappedRecords: 0,
            },
            recentJobs: [],
            isLoading: true,
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        this.state.isLoading = true;

        try {
            const [jobs, connections, templates, mappedRecords] = await Promise.all([
                this.orm.searchRead("migration.job", [], ["name", "template_id", "state", "start_time", "total_records", "success_records", "error_records", "progress_percent"], { limit: 10, order: "start_time desc, id desc" }),
                this.orm.searchRead("migration.connection", [], ["name", "conn_type", "state"]),
                this.orm.searchRead("migration.template", [], ["name", "target_model_name"]),
                this.orm.searchCount("migration.record.map", []),
            ]);

            let totalJobs = jobs.length;
            let successRecordsSum = jobs.reduce((sum, j) => sum + (j.success_records || 0), 0);
            let errorRecordsSum = jobs.reduce((sum, j) => sum + (j.error_records || 0), 0);

            this.state.stats = {
                totalJobs,
                successCount: successRecordsSum,
                errorCount: errorRecordsSum,
                activeConnections: connections.length,
                totalTemplates: templates.length,
                totalMappedRecords: mappedRecords,
            };

            this.state.recentJobs = jobs;
        } catch (error) {
            console.error("Failed to load migration dashboard statistics:", error);
        } finally {
            this.state.isLoading = false;
        }
    }

    async refreshDashboard() {
        await this.loadDashboardData();
    }

    openConnections() {
        this.action.doAction("data_migration.action_migration_connection");
    }

    openTemplates() {
        this.action.doAction("data_migration.action_migration_template");
    }

    openJobs() {
        this.action.doAction("data_migration.action_migration_job");
    }

    openAuditLogs() {
        this.action.doAction("data_migration.action_migration_log");
    }

    openJobDetail(jobId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "migration.job",
            res_id: jobId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    createNewConnection() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "New Data Connection",
            res_model: "migration.connection",
            views: [[false, "form"]],
            target: "current",
        });
    }

    createNewTemplate() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "New Mapping Template",
            res_model: "migration.template",
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("data_migration.dashboard", MigrationStudioDashboard);
