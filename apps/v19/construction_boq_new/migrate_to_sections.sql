-- ============================================================
-- Construction BOQ — Migration: capitulo/subcapitulo → section
-- Idempotent: safe to run multiple times (IF NOT EXISTS / DO NOTHING)
-- ============================================================

BEGIN;

-- STEP 1: Create construction_boq_section table
-- ============================================================
RAISE NOTICE 'Step 1: Creating construction_boq_section table...';

CREATE TABLE IF NOT EXISTS construction_boq_section (
    id                    SERIAL PRIMARY KEY,
    boq_id                INTEGER NOT NULL REFERENCES construction_boq(id) ON DELETE CASCADE,
    parent_id             INTEGER REFERENCES construction_boq_section(id) ON DELETE CASCADE,
    code                  VARCHAR NOT NULL DEFAULT '',
    name                  VARCHAR NOT NULL DEFAULT '',
    sequence              INTEGER NOT NULL DEFAULT 10,
    depth                 INTEGER NOT NULL DEFAULT 0,
    path                  VARCHAR,
    is_leaf               BOOLEAN NOT NULL DEFAULT TRUE,
    specialty             VARCHAR DEFAULT 'General',
    color                 VARCHAR DEFAULT '#1E3A5F',
    notes                 TEXT,
    analytic_account_id   INTEGER REFERENCES account_analytic_account(id),
    create_uid            INTEGER REFERENCES res_users(id),
    write_uid             INTEGER REFERENCES res_users(id),
    create_date           TIMESTAMP DEFAULT NOW(),
    write_date            TIMESTAMP DEFAULT NOW()
);

-- STEP 2: Create indexes
-- ============================================================
RAISE NOTICE 'Step 2: Creating indexes...';

CREATE INDEX IF NOT EXISTS construction_boq_section_boq_id_idx
    ON construction_boq_section(boq_id);
CREATE INDEX IF NOT EXISTS construction_boq_section_parent_id_idx
    ON construction_boq_section(parent_id);
CREATE INDEX IF NOT EXISTS construction_boq_section_path_idx
    ON construction_boq_section(path);
CREATE INDEX IF NOT EXISTS construction_boq_section_is_leaf_idx
    ON construction_boq_section(is_leaf);

-- STEP 3a: Migrate root sections from construction_boq_capitulo
-- ============================================================
RAISE NOTICE 'Step 3a: Migrating chapters to root sections...';

DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM construction_boq_capitulo;
    RAISE NOTICE '  Found % chapters to migrate', v_count;
END $$;

-- Temp table to track old_cap_id → new_section_id
CREATE TEMP TABLE IF NOT EXISTS _cap_section_map (
    old_cap_id  INTEGER PRIMARY KEY,
    new_sec_id  INTEGER
) ON COMMIT PRESERVE ROWS;

INSERT INTO construction_boq_section
    (boq_id, parent_id, code, name, sequence, depth, path,
     is_leaf, specialty, color, notes, analytic_account_id,
     create_uid, write_uid, create_date, write_date)
SELECT
    c.boq_id,
    NULL,
    c.code,
    c.name,
    c.sequence,
    0,
    LPAD(c.sequence::text, 4, '0'),
    FALSE,   -- chapters are not leaves (they have sub-chapters)
    COALESCE(c.specialty, 'General'),
    COALESCE(c.color, '#1E3A5F'),
    c.notes,
    c.analytic_account_id,
    c.create_uid,
    c.write_uid,
    c.create_date,
    c.write_date
FROM construction_boq_capitulo c
WHERE NOT EXISTS (
    SELECT 1 FROM construction_boq_section s
    WHERE s.boq_id = c.boq_id AND s.parent_id IS NULL AND s.code = c.code
)
RETURNING id;

-- Build cap mapping
INSERT INTO _cap_section_map (old_cap_id, new_sec_id)
SELECT c.id, s.id
FROM construction_boq_capitulo c
JOIN construction_boq_section s
    ON s.boq_id = c.boq_id AND s.parent_id IS NULL AND s.code = c.code
ON CONFLICT (old_cap_id) DO NOTHING;

-- STEP 3b: Migrate leaf sections from construction_boq_subcapitulo
-- ============================================================
RAISE NOTICE 'Step 3b: Migrating sub-chapters to leaf sections...';

DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM construction_boq_subcapitulo;
    RAISE NOTICE '  Found % sub-chapters to migrate', v_count;
END $$;

CREATE TEMP TABLE IF NOT EXISTS _sub_section_map (
    old_sub_id  INTEGER PRIMARY KEY,
    new_sec_id  INTEGER
) ON COMMIT PRESERVE ROWS;

INSERT INTO construction_boq_section
    (boq_id, parent_id, code, name, sequence, depth, path,
     is_leaf, specialty, color, notes,
     create_uid, write_uid, create_date, write_date)
SELECT
    sc.boq_id,
    m.new_sec_id,
    sc.code,
    sc.name,
    sc.sequence,
    1,
    LPAD(c.sequence::text, 4, '0') || '.' || LPAD(sc.sequence::text, 4, '0'),
    TRUE,
    'General',
    '#1E3A5F',
    sc.notes,
    sc.create_uid,
    sc.write_uid,
    sc.create_date,
    sc.write_date
FROM construction_boq_subcapitulo sc
JOIN _cap_section_map m ON m.old_cap_id = sc.capitulo_id
JOIN construction_boq_capitulo c ON c.id = sc.capitulo_id
WHERE NOT EXISTS (
    SELECT 1 FROM construction_boq_section s
    WHERE s.boq_id = sc.boq_id AND s.parent_id = m.new_sec_id AND s.code = sc.code
);

-- Build sub mapping
INSERT INTO _sub_section_map (old_sub_id, new_sec_id)
SELECT sc.id, s.id
FROM construction_boq_subcapitulo sc
JOIN _cap_section_map m ON m.old_cap_id = sc.capitulo_id
JOIN construction_boq_section s
    ON s.boq_id = sc.boq_id AND s.parent_id = m.new_sec_id AND s.code = sc.code
ON CONFLICT (old_sub_id) DO NOTHING;

-- STEP 4: Add section_id column to artigo table
-- ============================================================
RAISE NOTICE 'Step 4: Adding section_id column to construction_boq_artigo...';

ALTER TABLE construction_boq_artigo
    ADD COLUMN IF NOT EXISTS section_id INTEGER
    REFERENCES construction_boq_section(id) ON DELETE CASCADE;

-- STEP 5: Populate section_id from old subcapitulo_id
-- ============================================================
RAISE NOTICE 'Step 5: Migrating artigo.section_id from subcapitulo_id...';

UPDATE construction_boq_artigo a
SET section_id = m.new_sec_id
FROM _sub_section_map m
WHERE m.old_sub_id = a.subcapitulo_id
  AND a.section_id IS NULL;

DO $$
DECLARE
    v_migrated INTEGER;
    v_total    INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_migrated FROM construction_boq_artigo WHERE section_id IS NOT NULL;
    SELECT COUNT(*) INTO v_total    FROM construction_boq_artigo;
    RAISE NOTICE '  Migrated %/% articles', v_migrated, v_total;
END $$;

-- STEP 6: Create index on section_id
-- ============================================================
RAISE NOTICE 'Step 6: Creating index on artigo.section_id...';

CREATE INDEX IF NOT EXISTS construction_boq_artigo_section_id_idx
    ON construction_boq_artigo(section_id);

-- STEP 7 (OPTIONAL — uncomment after validating data integrity):
-- ============================================================
-- RAISE NOTICE 'Step 7: Dropping old columns and tables...';
-- ALTER TABLE construction_boq_artigo DROP COLUMN IF EXISTS capitulo_id;
-- ALTER TABLE construction_boq_artigo DROP COLUMN IF EXISTS subcapitulo_id;
-- DROP TABLE IF EXISTS construction_boq_subcapitulo;
-- DROP TABLE IF EXISTS construction_boq_capitulo;

RAISE NOTICE 'Migration complete.';

COMMIT;
