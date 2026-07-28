# Desplegar CardMax MX

Arquitectura pública:
- **Frontend** (React/Vite) → Vercel
- **Backend API** (FastAPI) → Render
- **Scraper** → GitHub Actions (cron diario, ya NO tu PC)
- **DB** → Supabase (ya existe)

---

## 1. Backend en Render

1. Entra a **render.com** → New → **Web Service** → conecta el repo `ruizpicazzo/CCOpti`.
2. Render detecta `render.yaml`. Confirma: rootDir `backend`, start `uvicorn app.main:app`.
3. En **Environment**, agrega estos secretos (los valores de tu `.env`):
   - `ANTHROPIC_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_KEY` (anon)
   - `SUPABASE_SERVICE_KEY`
   - `ADMIN_TOKEN`
   - `ALLOWED_ORIGINS` → **la URL de tu frontend en Vercel** (paso 2), ej. `https://cardmax.vercel.app`
4. Deploy. Copia la URL final, ej. `https://cardmax-api.onrender.com`.

> Nota: el plan free de Render "duerme" tras inactividad; la primera visita tras dormir tarda ~30s.

## 2. Frontend en Vercel

1. Entra a **vercel.com** → New Project → importa `ruizpicazzo/CCOpti`.
2. **Root Directory** = `frontend`. Framework = Vite (autodetectado).
3. En **Environment Variables** agrega:
   - `VITE_API_URL` = la URL del backend de Render (paso 1), ej. `https://cardmax-api.onrender.com`
4. Deploy. Copia la URL, ej. `https://cardmax.vercel.app`.
5. **Regresa a Render** y pon esa URL en `ALLOWED_ORIGINS` (si no lo hiciste). Redeploy el backend.

## 3. Scraper en GitHub Actions

1. En GitHub → repo → **Settings → Secrets and variables → Actions → New repository secret**. Agrega:
   - `ANTHROPIC_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `SUPABASE_SERVICE_KEY`
2. El workflow `.github/workflows/scraper.yml` corre diario a las **00:01 hora de México**. Pruébalo manual: pestaña **Actions → Daily Promo Scraper → Run workflow**.
3. **Desactiva el scraper local** para no scrapear doble (doble gasto de tokens):
   ```powershell
   Disable-ScheduledTask -TaskName "CardMax Scraper"
   ```

## 4. Supabase — RLS (seguridad de la DB)

En **Table Editor → promotions**: activa **RLS** y agrega una política de solo lectura pública (plantilla "Enable read access for all users"). El scraper sigue escribiendo con la `service_role` key.

---

## Checklist antes de compartir el link
- [ ] Backend Render responde en `/health`
- [ ] Frontend Vercel carga y hace consultas
- [ ] `ALLOWED_ORIGINS` en Render = dominio de Vercel
- [ ] Secretos de Actions puestos + workflow probado
- [ ] Scraper local desactivado
- [ ] RLS activado en Supabase
- [ ] (Recomendado) revisar términos de los bancos antes de un lanzamiento amplio
