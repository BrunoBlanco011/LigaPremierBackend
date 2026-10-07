-- =====================================================================
-- Defensa en profundidad (ver docs/SEGURIDAD.md)
-- =====================================================================

-- 1) Solo el backend (service_role) toca las tablas. RLS ya bloquea a anon y
--    authenticated; ademas se les quitan los permisos para que, si alguien
--    agrega una politica por error, la anon key siga sin poder leer ni escribir.
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke execute on all functions in schema public from anon, authenticated;

-- Lo mismo para las tablas/funciones que se creen en el futuro
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke execute on functions from anon, authenticated;

-- 2) Bucket de logos: solo imagenes raster y maximo 2 MB (SVG fuera: puede llevar JavaScript)
update storage.buckets
set allowed_mime_types = array['image/png', 'image/jpeg', 'image/webp'],
    file_size_limit    = 2 * 1024 * 1024
where id = 'team-logos';
