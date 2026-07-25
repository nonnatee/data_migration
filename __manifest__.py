# -*- coding: utf-8 -*-
{
    'name': 'Data Migration Tools Studio',
    'version': '19.0.1.0.0',
    'category': 'Tools/ETL',
    'summary': 'Enterprise Data Migration & ETL Engine for Odoo 19 with CSV, Excel, JSON, Visual FoxPro DBF, ODBC, SQL & Odoo RPC support.',
    'description': """
Data Migration Studio for Odoo 19
=================================
A comprehensive ETL and data synchronization module designed for seamless migration into Odoo 19.

Key Features:
-------------
* **Multi-Source Connectors**: CSV, Excel (.xlsx/.xls), JSON files, Visual FoxPro DBF (.dbf & .fpt memo files), ODBC (DSN & connection strings), PostgreSQL, MySQL, SQL Server, and Odoo XML-RPC/JSON-RPC.
* **Visual Field Mapping**: Target model introspection, field-to-field mapping, value conversion maps, default values, and custom Python transformation snippets.
* **Relational Lookups**: Automated resolution for Many2one and Many2many fields by XML ID, key fields (e.g., ref, vat, email), search domain, or auto-creation.
* **Upsert & Change Tracking**: Create, Update, Upsert (Update or Create), and Skip modes with persistent `ir.model.data` & checksum tracking.
* **Savepoint Error Isolation**: Chunked batch processing with `with self.env.cr.savepoint():` per row, preventing single-record failures from aborting the entire run.
* **Interactive OWL 3 Dashboard**: Live job statistics, failure distribution analysis, error log search, and CSV export.
    """,
    'author': 'Nonnatee Kanjana',
    'website': 'https://odoo.ps-groups.com',
    'license': 'LGPL-3',
    'icon': '/data_migration/static/description/icon.png',
    'depends': ['base', 'web'],
    'data': [
        'security/data_migration_security.xml',
        'security/ir.model.access.csv',
        'views/migration_connection_views.xml',
        'views/migration_template_views.xml',
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
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
