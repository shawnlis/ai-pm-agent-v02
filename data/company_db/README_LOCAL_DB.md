# Local Company Database

`company_research.sqlite` is a local generated database and is not intended for GitHub upload.

For repository use:

- Keep the real database at `data/company_db/company_research.sqlite` on the local machine only.
- The schema-only export is in `company_research_schema.sql`; it contains table/index definitions only and no row data.
- Recreate or refresh the database from local research outputs with the existing company DB import/report scripts after configuring local credentials.
- Do not commit `.sqlite`, `.db`, `.parquet`, model, output, cache, or report artifacts.
