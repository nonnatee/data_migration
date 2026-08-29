# -*- coding: utf-8 -*-
{
    'name': 'Data Migration Tools Studio',
    'version': '19.0.1.0.0',
    'category': 'Tools/ETL',
    'summary': 'Enterprise Data Migration & ETL Studio for Odoo 19 with SQL, Files, APIs, Cloud Storage, AI Transformation & Validation.',
    'description': """
Data Migration Studio for Odoo 19
=================================
An Enterprise 6-Stage ETL and data synchronization platform designed for seamless migration into Odoo 19.

6 Key Stages:
-------------
1. **Data Source Connection**: SQL databases (PostgreSQL, MySQL, SQL Server, Oracle, SQLite, ODBC, Visual FoxPro DBF), Files (Excel, CSV, TSV, JSON, XML), REST APIs, GraphQL, Cloud Storage (AWS S3, Google Cloud, Azure, SFTP), Google Sheets, and Odoo XML-RPC.
2. **Data Extraction**: Custom SQL queries with parameter binding, incremental watermarks, REST/GraphQL pagination extractors, and schema introspection.
3. **Data Transformation (AI Integration)**: Cleansing (deduplication, null handling, regex sanitization), Normalization (data types, date standardizer, unit conversions, phone/address formatting), Business Logic (math calculations, case-when branching, Python sandbox), and AI Prompt NLP Transformers.
4. **Data Loading**: Upsert, Create Only, Update Only, and Skip modes with XML ID tracking, composite key matching, Many2one/Many2many resolution, and chunked savepoint transaction isolation.
5. **Validation (AI Integration)**: Pre-load and Post-load validation rules (mandatory, regex format, range boundaries, foreign key existence, business integrity) and AI Anomaly Detection with Quality Health Scoring.
6. **Monitoring & Logging**: Multi-stage Migration Plan orchestrator, live execution audit stream, throughput metrics, and interactive OWL 3 Console & Dashboard.
    """,
    'author': 'Nonnatee Kanjana',
    'website': 'https://odoo.ps-groups.com',
    'license': 'LGPL-3',
    'icon': '/data_migration/static/description/icon.png',
    'depends': ['base', 'web'],
    'data': [
        'security/data_migration_security.xml',
        'security/ir.model.access.csv',
        'data/migration_template_data.xml',
        'data/migration_plan_data.xml',
        'views/migration_ai_config_views.xml',
        'views/migration_connection_views.xml',
        'views/migration_extraction_views.xml',
        'views/migration_template_views.xml',
        'views/migration_plan_views.xml',
        'views/migration_transform_template_views.xml',
        'views/migration_mapping_transform_views.xml',
        'views/migration_job_views.xml',
        'views/migration_log_views.xml',
        'views/migration_record_map_views.xml',
        'views/migration_dashboard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'data_migration/static/src/components/migration_dashboard/migration_dashboard.js',
            'data_migration/static/src/components/migration_dashboard/migration_dashboard.xml',
            'data_migration/static/src/components/migration_dashboard/migration_dashboard.scss',
            'data_migration/static/src/components/visual_mapper/visual_mapper.js',
            'data_migration/static/src/components/visual_mapper/visual_mapper.xml',
            'data_migration/static/src/components/visual_mapper/visual_mapper.scss',
            'data_migration/static/src/components/visual_extraction_builder/visual_extraction_builder.js',
            'data_migration/static/src/components/visual_extraction_builder/visual_extraction_builder.xml',
            'data_migration/static/src/components/visual_extraction_builder/visual_extraction_builder.scss',
            'data_migration/static/src/components/migration_plan_console/migration_plan_console.js',
            'data_migration/static/src/components/migration_plan_console/migration_plan_console.xml',
            'data_migration/static/src/components/migration_plan_console/migration_plan_console.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
