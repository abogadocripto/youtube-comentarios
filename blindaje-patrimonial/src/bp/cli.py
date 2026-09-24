"""Línea de órdenes `bp` (docs/01 §4, docs/12).

Órdenes:
  doctor          comprueba configuración, prompts, esquemas y variables de entorno (sin mostrar secretos)
  demo            ejecuta el Daily completo sin red ni BD (historia sintética + fixtures) y escribe out/demo/
  ingest-daily    ingesta de fuentes del Daily (08:30 Madrid)
  build-daily     derivar → analizar → seleccionar → LLM → validar → borrador (08:45 Madrid)
  publish-daily   publica el borrador en Telegram de forma idempotente (09:00 Madrid)
  run-daily       ingest + build + publish en un solo proceso (respaldo externo con --only-if-missing)
  smoke           prueba en vivo de los conectores (desde el VPS); --record graba fixtures reales
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from bp.config import load_config, validate
from bp.models import MADRID, RunContext, utcnow

UTC = timezone.utc


def _ctx(args: argparse.Namespace, offline: bool = False) -> RunContext:
    now = datetime.fromisoformat(args.now).astimezone(UTC) if getattr(args, "now", None) else utcnow()
    rd = date.fromisoformat(args.date) if getattr(args, "date", None) else now.astimezone(MADRID).date()
    return RunContext(report_date=rd, now=now, offline=offline or getattr(args, "offline", False),
                      dry_run=getattr(args, "dry_run", False))


def _store():
    url = os.environ.get("BP_DATABASE_URL")
    if not url:
        raise SystemExit("BP_DATABASE_URL no definida (las órdenes de producción requieren PostgreSQL; use `bp demo` para ensayar)")
    from bp.store.postgres import PostgresStore
    return PostgresStore(url)


def _backend(cfg, kind: str):
    from bp.llm.client import LLMError, default_backend
    if kind == "none":
        return None
    try:
        return default_backend(cfg)
    except LLMError as exc:
        print(f"[aviso] {exc}: se usará la lectura por plantillas", file=sys.stderr)
        return None


def _fixtures(args) -> Path | None:
    if getattr(args, "fixtures", None):
        return Path(args.fixtures)
    return load_config().root / "tests" / "fixtures" if getattr(args, "offline", False) else None


# ─── órdenes ──────────────────────────────────────────────────────────────────────────────────────────────

def cmd_doctor(args) -> int:
    cfg = load_config()
    problems = validate(cfg)
    from bp.schemas import validate_instance
    ex = cfg.root / "schema" / "examples"
    for inst, sch in (("daily_input.example.json", "daily_input.schema.json"), ("daily_output.example.json", "daily_output.schema.json")):
        p = ex / inst
        if p.exists():
            problems += [f"{inst}: {e}" for e in validate_instance(json.loads(p.read_text("utf-8")), sch, cfg.root)]
    for call in cfg.llm["calls"].values():
        for key in ("prompt_system", "prompt_user"):
            if call.get(key) and not cfg.prompt_path(call[key]).exists():
                problems.append(f"falta el prompt {call[key]}")
    env = {"BP_DATABASE_URL": "BD", "ANTHROPIC_API_KEY": "LLM", "TELEGRAM_PUBLISHER_TOKEN": "Telegram (publicador)",
           "TELEGRAM_CHANNEL_ID": "canal público", "TELEGRAM_ADMIN_CHAT_ID": "chat de edición", "HC_DAILY_BUILD": "Healthchecks"}
    print(f"configuración: {len(cfg.metrics)} métricas · {len(cfg.sources)} fuentes · rules_version {cfg.rules['rules_version']}")
    for k, what in env.items():
        print(f"  {'✔' if os.environ.get(k) else '·'} {k:<26} {what}")
    for s_id, s in sorted(cfg.sources.items()):
        auth = s.get("auth") or {}
        if auth.get("env") and not os.environ.get(auth["env"]):
            print(f"  · {auth['env']:<26} clave de {s_id} (sin definir)")
    if problems:
        print("PROBLEMAS:")
        for p in problems:
            print("  ✘", p)
        return 1
    print("OK")
    return 0


def _write_outputs(out_dir: Path, result, store=None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "fact_sheet.json").write_text(json.dumps(result.fact_sheet, ensure_ascii=False, indent=1), "utf-8")
    (out_dir / "validation.json").write_text(json.dumps(result.reports, ensure_ascii=False, indent=1, default=str), "utf-8")
    (out_dir / "excluded.json").write_text(json.dumps(result.excluded, ensure_ascii=False, indent=1), "utf-8")
    if result.output is not None:
        (out_dir / "llm_output.json").write_text(json.dumps(result.output.model_dump(), ensure_ascii=False, indent=1), "utf-8")
    if result.rendered is not None:
        (out_dir / "daily_telegram.html").write_text(result.rendered.html, "utf-8")
        (out_dir / "daily_plain.txt").write_text(result.rendered.plain, "utf-8")


def cmd_demo(args) -> int:
    from bp.demo import DemoBackend, seed_history
    from bp.ingest.registry import run_daily_ingest
    from bp.orchestrator.daily import build_daily
    from bp.store.memory import MemoryStore

    cfg = load_config()
    rd = date.fromisoformat(args.date)
    now = datetime.fromisoformat(args.now).astimezone(UTC) if args.now else datetime(rd.year, rd.month, rd.day, 6, 50, tzinfo=UTC)
    ctx = RunContext(report_date=rd, now=now, offline=True)
    store = MemoryStore()
    seed_history(store, rd)
    runs = run_daily_ingest(ctx, cfg, store, fixtures_dir=cfg.root / "tests" / "fixtures")
    for r in runs:
        print(f"  {'✔' if r.ok else '✘'} {r.connector:<12} {len(r.observations):>4} obs {r.error or ''}")
    if args.llm == "static":
        backend = DemoBackend()
    elif args.llm == "anthropic":
        backend = _backend(cfg, "anthropic")
    else:
        backend = None
    result = build_daily(ctx, cfg, store, backend, verify_with_llm=args.llm != "none")
    out_dir = Path(args.out)
    _write_outputs(out_dir, result)
    print(f"estado: {result.status} · origen: {result.origin} · motivo: {result.reason or '—'}")
    for rep in result.reports:
        for c in rep.get("checks", []):
            if not c["passed"]:
                print(f"  [{c['severity']}] {c['check_id']} {c['path']}: {c['details']}")
    if result.rendered:
        print("─" * 60)
        print(result.rendered.plain)
        print("─" * 60)
        print(f"{result.rendered.visible_chars} caracteres visibles · salida en {out_dir}/")
    return 0 if result.status in ("validated", "fallback") else 2


def cmd_ingest_daily(args) -> int:
    from bp.ingest.registry import run_daily_ingest
    from bp.observability.heartbeat import ping
    cfg, store, ctx = load_config(), _store(), _ctx(args)
    ping("DAILY_INGEST", "/start")
    runs = run_daily_ingest(ctx, cfg, store, fixtures_dir=_fixtures(args), only=args.only)
    failed = [r for r in runs if not r.ok]
    for r in runs:
        print(f"{'✔' if r.ok else '✘'} {r.connector:<12} {len(r.observations):>4} obs {r.error or ''}")
    store.log_job("ingest_daily", f"ingest_daily:{ctx.report_date}", "ok" if not failed else "partial",
                  {"ok": len(runs) - len(failed), "failed": [r.connector for r in failed]})
    ping("DAILY_INGEST", "" if not failed else "/fail")
    return 0 if len(failed) < len(runs) else 1


def cmd_build_daily(args) -> int:
    from bp.observability.heartbeat import ping
    from bp.orchestrator.daily import build_daily
    cfg, store, ctx = load_config(), _store(), _ctx(args)
    ping("DAILY_BUILD", "/start")
    result = build_daily(ctx, cfg, store, _backend(cfg, args.llm), verify_with_llm=not args.no_verify)
    if args.out:
        _write_outputs(Path(args.out), result)
    store.log_job("build_daily", f"build_daily:{ctx.report_date}", result.status, {"origin": result.origin}, result.reason)
    print(f"estado: {result.status} · origen: {result.origin} · motivo: {result.reason or '—'}")
    _notify_admin(cfg, ctx, result)
    ping("DAILY_BUILD", "" if result.status in ("validated", "fallback") else "/fail")
    return 0 if result.status in ("validated", "fallback") else 2


def _notify_admin(cfg, ctx, result) -> None:
    """Avisa al chat de edición del resultado del borrador (sin datos sensibles)."""
    chat = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    token = os.environ.get("TELEGRAM_ADMIN_TOKEN") or os.environ.get("TELEGRAM_PUBLISHER_TOKEN")
    if not chat or not token:
        return
    from html import escape

    from bp.distribution.telegram import TelegramClient, TelegramError
    icon = {"validated": "✅", "fallback": "🟡", "withheld": "⛔"}.get(result.status, "❔")
    text = f"{icon} Daily {ctx.report_date.isoformat()}: <b>{escape(result.status)}</b>"
    if result.reason:
        text += f"\n{escape(result.reason[:500])}"
    try:
        TelegramClient(token=token).send_message(chat, text, disable_notification=result.status == "validated")
    except TelegramError as exc:
        print(f"[aviso] no se pudo avisar al chat de edición: {exc}", file=sys.stderr)


def cmd_publish_daily(args) -> int:
    from bp.distribution.telegram import TelegramClient
    from bp.observability.heartbeat import ping
    from bp.orchestrator.daily import publish_daily
    cfg, store, ctx = load_config(), _store(), _ctx(args)
    chat_id = args.chat_id or os.environ.get("TELEGRAM_CHANNEL_ID")
    if not chat_id:
        raise SystemExit("TELEGRAM_CHANNEL_ID no definida")
    if args.only_if_missing:
        rep = store.get_daily_report(ctx.report_date)
        if rep and rep.get("status") in ("published", "corrected"):
            print("ya publicado: nada que hacer")
            return 0
    if args.dry_run:
        rep = store.get_daily_report(ctx.report_date) or {}
        print(rep.get("rendered_telegram") or f"sin borrador (estado: {rep.get('status')})")
        return 0
    res = publish_daily(ctx, cfg, store, TelegramClient(), chat_id, force=args.force)
    store.log_job("publish_daily", f"publish_daily:{ctx.report_date}", res.status, {"message_id": res.message_id}, res.error)
    print(f"publicación: {res.status} {res.message_id or ''} {res.error or ''}")
    ping("DAILY_PUBLISH", "" if res.status in ("sent", "skipped_duplicate") else "/fail")
    return 0 if res.status in ("sent", "skipped_duplicate") else 1


def cmd_run_daily(args) -> int:
    store = _store()
    ctx = _ctx(args)
    if args.only_if_missing:
        rep = store.get_daily_report(ctx.report_date)
        if rep and rep.get("status") in ("published", "corrected"):
            print("ya publicado: nada que hacer")
            return 0
    rc = cmd_ingest_daily(args)
    if rc != 0:
        print("[aviso] ingesta con errores: se continúa con los datos disponibles", file=sys.stderr)
    rc = cmd_build_daily(args)
    if rc != 0:
        return rc
    return cmd_publish_daily(args)


def cmd_smoke(args) -> int:
    from bp.ingest.registry import DAILY_CONNECTORS
    from bp.store.memory import MemoryStore
    cfg = load_config()
    ctx = RunContext(report_date=utcnow().astimezone(MADRID).date(), now=utcnow(), offline=False)
    store = MemoryStore()
    bad = 0
    for cls in DAILY_CONNECTORS:
        if args.only and cls.id not in args.only:
            continue
        conn = cls(cfg)
        run = conn.run(ctx, store)
        latest: dict[str, Any] = {}
        for o in run.observations:
            if o.metric_id not in latest or o.as_of > latest[o.metric_id].as_of:
                latest[o.metric_id] = o
        print(f"{'✔' if run.ok else '✘'} {cls.id:<12} {len(run.observations):>4} obs {run.error or ''}")
        for mid, o in sorted(latest.items()):
            print(f"     {mid:<28} {o.value!s:<22} as_of {o.as_of.isoformat()}")
        bad += not run.ok
        if args.record and run.ok:
            for raw in store.raw[-len(run.raw_ids):] if run.raw_ids else []:
                if not raw.fixture:
                    continue
                path = cfg.root / "tests" / "fixtures" / cls.id / raw.fixture
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw.body)
                print(f"     grabado {path.relative_to(cfg.root)}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bp", description="Blindaje Patrimonial — sistema de inteligencia patrimonial")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, llm=True):
        sp.add_argument("--date", help="fecha de publicación (Madrid), AAAA-MM-DD; por defecto hoy")
        sp.add_argument("--now", help="instante ISO-8601 simulado (reejecuciones y pruebas)")
        sp.add_argument("--offline", action="store_true", help="usar fixtures en lugar de la red")
        sp.add_argument("--fixtures", help="directorio de fixtures (modo offline)")
        sp.add_argument("--only", nargs="*", help="solo estos conectores")
        if llm:
            sp.add_argument("--llm", choices=["anthropic", "none"], default="anthropic")
            sp.add_argument("--no-verify", action="store_true", help="omitir el verificador LLM independiente")
            sp.add_argument("--out", help="escribir también los artefactos en este directorio")

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    d = sub.add_parser("demo")
    d.add_argument("--date", default="2026-09-24")
    d.add_argument("--now")
    d.add_argument("--llm", choices=["static", "none", "anthropic"], default="none")
    d.add_argument("--out", default="out/demo")
    d.set_defaults(fn=cmd_demo)
    sp = sub.add_parser("ingest-daily")
    common(sp, llm=False)
    sp.set_defaults(fn=cmd_ingest_daily)
    sp = sub.add_parser("build-daily")
    common(sp)
    sp.set_defaults(fn=cmd_build_daily)
    for name, fn in (("publish-daily", cmd_publish_daily), ("run-daily", cmd_run_daily)):
        sp = sub.add_parser(name)
        common(sp, llm=name == "run-daily")
        sp.add_argument("--chat-id")
        sp.add_argument("--force", action="store_true", help="publicar después de las 10:30 (confirmación humana)")
        sp.add_argument("--only-if-missing", action="store_true", help="no hacer nada si ya se publicó hoy")
        sp.add_argument("--dry-run", action="store_true")
        sp.set_defaults(fn=fn)
    sp = sub.add_parser("smoke")
    sp.add_argument("--only", nargs="*")
    sp.add_argument("--record", action="store_true", help="grabar las respuestas reales como fixtures")
    sp.set_defaults(fn=cmd_smoke)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
