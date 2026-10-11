-- =====================================================================
--  Row Level Security (RLS) for the Abyssinia Hotel database (PostgreSQL)
--
--  How the site is built: the browser never talks to the database. It only
--  calls the Flask API, and Flask connects with ONE server-side connection
--  string (DATABASE_URL). So the correct RLS setup is "deny everything to
--  every other role" - then even if someone finds your database URL, your
--  project URL, or a public/anon key (e.g. on Supabase), they cannot read
--  or change a single row through the database's own API.
--
--  Flask keeps working because it connects as the table OWNER, and owners
--  bypass RLS. (Do NOT add FORCE ROW LEVEL SECURITY - it would lock Flask out.)
--
--  Run this ONCE in your database's SQL editor, AFTER deploying the new code
--  (the first deploy creates the new "rate_limit" table). It is safe to run
--  again whenever you add tables.
-- =====================================================================

-- 1) Turn on RLS for every table. With RLS on and NO policies, all
--    non-owner roles are denied by default.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['admin', 'booking', 'menu_item', 'order', 'rate_limit'] LOOP
    IF to_regclass(format('public.%I', t)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    END IF;
  END LOOP;
END $$;

-- 2) Belt and braces: also remove table privileges from the public-facing
--    roles used by Supabase's auto-generated API (skipped if the roles don't exist).
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
      EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
      EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
    END IF;
  END LOOP;
END $$;

-- 3) CHECK: every table below should show rls_enabled = true
SELECT c.relname AS table_name, c.relrowsecurity AS rls_enabled
FROM pg_class c
WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
ORDER BY c.relname;

-- ---------------------------------------------------------------------
-- ONLY if Flask connects as a role that does NOT own the tables (rare):
-- Flask would then be blocked too, so give that one role a policy.
-- Replace app_user with that role's name, then uncomment and run:
--
-- DO $$
-- DECLARE t text;
-- BEGIN
--   FOREACH t IN ARRAY ARRAY['admin', 'booking', 'menu_item', 'order', 'rate_limit'] LOOP
--     EXECUTE format('CREATE POLICY app_full_access ON public.%I FOR ALL TO app_user USING (true) WITH CHECK (true)', t);
--   END LOOP;
-- END $$;
-- ---------------------------------------------------------------------
