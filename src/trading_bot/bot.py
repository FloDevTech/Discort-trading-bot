from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from decimal import Decimal

import discord
from discord import app_commands
from discord.ext import tasks

from trading_bot.core.scanner_config import ScannerConfig, ScannerConfigStore, load_env_file
from trading_bot.core.risk import PlanValidationError, build_trading_plan_from_strings
from trading_bot.core.stock_scanner import StockScanner
from trading_bot.formatters import (
    format_scanner_config_for_discord,
    format_plan_for_discord,
    format_stock_scan_for_discord,
    split_discord_message,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PurgeResult:
    deleted_count: int
    error: str | None = None


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if not value:
        return None
    return int(value)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _parse_decimal_option(value: str | None, field_name: str) -> float | None:
    if value is None:
        return None

    normalized = value.strip().replace(",", ".")
    if normalized.startswith("."):
        normalized = f"0{normalized}"
    if normalized.startswith("-."):
        normalized = normalized.replace("-.", "-0.", 1)

    try:
        return float(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} debe ser un numero. Ej: 0.1") from exc


class TradingBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.scanner_config_store = ScannerConfigStore()
        self.scanner_config = self.scanner_config_store.load()
        self.stock_scanner = StockScanner(filters=self.scanner_config.filters)
        self.stock_scanner_channel_id = _optional_int_env("DISCORD_STOCK_SCANNER_CHANNEL_ID")
        self.last_plan_commission = Decimal("0")
        self.stock_scanner_loop.change_interval(
            minutes=self.scanner_config.interval_minutes
        )

    async def setup_hook(self) -> None:
        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

        if self.stock_scanner_channel_id and not self.stock_scanner_loop.is_running():
            self.stock_scanner_loop.start()

    @tasks.loop(minutes=5)
    async def stock_scanner_loop(self) -> None:
        try:
            if not self.stock_scanner_channel_id:
                return

            channel = self.get_channel(self.stock_scanner_channel_id)
            if channel is None:
                channel = await self.fetch_channel(self.stock_scanner_channel_id)

            scan = await asyncio.to_thread(self.stock_scanner.scan)
            await _clear_channel_before_scanner_post(channel)
            for message in split_discord_message(format_stock_scan_for_discord(scan)):
                await channel.send(message)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("Error ejecutando stock_scanner_loop")

    @stock_scanner_loop.before_loop
    async def before_stock_scanner_loop(self) -> None:
        await self.wait_until_ready()

    def update_scanner_config(self, config: ScannerConfig) -> None:
        self.scanner_config = config
        self.stock_scanner.filters = config.filters
        self.stock_scanner_loop.change_interval(minutes=config.interval_minutes)
        self.scanner_config_store.save(config)


load_env_file()
client = TradingBot()


@client.tree.command(
    name="plan-trading",
    description="Calcula fases, riesgo y acciones de un plan de trading.",
)
@app_commands.describe(
    fases="Numero de fases del plan.",
    riesgo_total="Riesgo total en dolares. Ej: 5",
    entradas="Precios separados por coma. Ej: 0.52,0.53,0.54",
    margenes="Margenes al stop separados por coma. Ej: 0.05,0.05,0.05",
    porcentajes="Porcentajes de riesgo separados por coma. Ej: 25,35,40",
    r_objetivo="Multiplo R para calcular TP. Ej: 3",
    comision="Comision por accion. Si lo omites, usa la ultima comision escrita.",
)
async def plan_trading(
    interaction: discord.Interaction,
    fases: int,
    riesgo_total: str,
    entradas: str,
    margenes: str,
    porcentajes: str,
    r_objetivo: str = "3",
    comision: str | None = None,
) -> None:
    plan_commission = comision if comision is not None else f"{client.last_plan_commission:f}"
    try:
        plan = build_trading_plan_from_strings(
            phases_count=fases,
            total_risk=riesgo_total,
            target_r=r_objetivo,
            commission=plan_commission,
            entries=entradas,
            stop_margins=margenes,
            risk_percentages=porcentajes,
        )
    except PlanValidationError as exc:
        await interaction.response.send_message(f"Error: {exc}", ephemeral=True)
        return

    if comision is not None:
        client.last_plan_commission = plan.commission
    await interaction.response.send_message(format_plan_for_discord(plan))


@client.tree.command(
    name="scanner-preview",
    description="Ejecuta ahora el scanner de acciones y muestra el resultado.",
)
async def scanner_preview(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)
    scan = await asyncio.to_thread(client.stock_scanner.scan)
    if interaction.channel is None:
        await interaction.followup.send("Error: no pude acceder a este canal.", ephemeral=True)
        return

    await _clear_channel_before_scanner_post(interaction.channel)
    messages = split_discord_message(format_stock_scan_for_discord(scan))
    for message in messages:
        await interaction.channel.send(message)
    await interaction.followup.send("Scanner publicado.", ephemeral=True)


@client.tree.command(
    name="scanner-config",
    description="Muestra los parametros actuales del scanner.",
)
async def scanner_config(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        format_scanner_config_for_discord(client.scanner_config),
        ephemeral=True,
    )


@client.tree.command(
    name="clean",
    description="Borra mensajes del canal actual.",
)
@app_commands.describe(
    limit="Cantidad maxima de mensajes a borrar. Por defecto 100.",
)
async def clean_channel(interaction: discord.Interaction, limit: int = 100) -> None:
    if interaction.channel is None:
        await interaction.response.send_message("Error: no pude acceder a este canal.", ephemeral=True)
        return

    if limit < 1 or limit > 1000:
        await interaction.response.send_message("Error: limit debe estar entre 1 y 1000.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    result = await _purge_channel(interaction.channel, limit=limit, bulk=False)
    if result.error:
        await interaction.followup.send(f"No pude limpiar el canal: {result.error}", ephemeral=True)
        return
    await interaction.followup.send(
        f"Canal limpiado. Mensajes borrados: {result.deleted_count}.",
        ephemeral=True,
    )


@client.tree.command(
    name="scanner-set",
    description="Modifica parametros del scanner desde Discord.",
)
@app_commands.describe(
    max_price="Precio maximo. Ej: 2",
    min_price="Precio minimo. Ej: 0.1 o .1",
    max_market_cap="Market cap maximo. Ej: 150000000",
    min_market_cap="Market cap minimo. Ej: 1000000",
    min_volume="Volumen minimo. Ej: 500000",
    min_change_percent="Movimiento minimo de precio en porcentaje. Ej: 50",
    min_float_rotation="Rotacion minima del float. Ej: 0.5 o .5",
    limit="Cantidad maxima de resultados. Ej: 10",
    max_symbols="Cantidad de tickers a enriquecer desde Finviz. Ej: 120",
    interval_minutes="Cada cuantos minutos publica el scanner. Ej: 5",
    symbols="Lista manual opcional de tickers separados por coma. Ej: DFSC,MDXH,SURG",
)
async def scanner_set(
    interaction: discord.Interaction,
    max_price: str | None = None,
    min_price: str | None = None,
    max_market_cap: int | None = None,
    min_market_cap: int | None = None,
    min_volume: int | None = None,
    min_change_percent: str | None = None,
    min_float_rotation: str | None = None,
    limit: int | None = None,
    max_symbols: int | None = None,
    interval_minutes: str | None = None,
    symbols: str | None = None,
) -> None:
    changes = {}
    try:
        if max_price is not None:
            changes["max_price"] = _parse_decimal_option(max_price, "max_price")
        if min_price is not None:
            changes["min_price"] = _parse_decimal_option(min_price, "min_price")
        if min_change_percent is not None:
            changes["min_change_percent"] = _parse_decimal_option(
                min_change_percent,
                "min_change_percent",
            )
        if min_float_rotation is not None:
            changes["min_float_rotation"] = _parse_decimal_option(
                min_float_rotation,
                "min_float_rotation",
            )
        next_interval = client.scanner_config.interval_minutes
        if interval_minutes is not None:
            parsed_interval = _parse_decimal_option(interval_minutes, "interval_minutes")
            assert parsed_interval is not None
            if parsed_interval < 1 or parsed_interval > 120:
                raise ValueError("interval_minutes debe estar entre 1 y 120.")
            next_interval = parsed_interval
    except ValueError as exc:
        await interaction.response.send_message(f"Error: {exc}", ephemeral=True)
        return

    if max_market_cap is not None:
        changes["max_market_cap"] = max_market_cap
    if min_market_cap is not None:
        changes["min_market_cap"] = min_market_cap
    if min_volume is not None:
        changes["min_volume"] = min_volume
    if limit is not None:
        changes["limit"] = limit
    if max_symbols is not None:
        changes["max_symbols_to_enrich"] = max_symbols
    if symbols is not None:
        if symbols.strip().lower() in {"auto", "finviz", "none", "ninguno"}:
            changes["symbols"] = ()
        else:
            changes["symbols"] = tuple(item.strip().upper() for item in symbols.split(",") if item.strip())

    try:
        filters = client.scanner_config.filters.updated(**changes)
        next_config = ScannerConfig(filters=filters, interval_minutes=next_interval)
    except ValueError as exc:
        await interaction.response.send_message(f"Error: {exc}", ephemeral=True)
        return

    client.update_scanner_config(next_config)
    await interaction.response.send_message(
        "Configuracion del scanner actualizada.\n\n"
        + format_scanner_config_for_discord(client.scanner_config),
        ephemeral=True,
    )


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Falta DISCORD_TOKEN. Configuralo en el archivo .env.")
    client.run(token)


async def _clear_channel_before_scanner_post(channel: object) -> None:
    result = await _purge_channel(
        channel,
        limit=_int_env("STOCK_SCANNER_CLEAR_LIMIT", 100),
        bulk=False,
    )
    if result.error:
        logger.warning("No pude limpiar el canal del scanner: %s", result.error)


async def _purge_channel(channel: object, limit: int, bulk: bool) -> PurgeResult:
    permissions_error = _channel_permissions_error(channel)
    if permissions_error:
        return PurgeResult(deleted_count=0, error=permissions_error)

    purge = getattr(channel, "purge", None)
    if purge is None:
        return PurgeResult(
            deleted_count=0,
            error="este tipo de canal no soporta borrado masivo.",
        )

    try:
        deleted = await purge(limit=limit, bulk=bulk)
        return PurgeResult(deleted_count=len(deleted))
    except discord.Forbidden:
        return PurgeResult(
            deleted_count=0,
            error="me falta el permiso Manage Messages en este canal.",
        )
    except discord.HTTPException:
        logger.exception("Discord rechazo la limpieza del canal del scanner.")
        return PurgeResult(
            deleted_count=0,
            error="Discord rechazo la limpieza. Prueba con un limit mas bajo.",
        )


def _channel_permissions_error(channel: object) -> str | None:
    guild = getattr(channel, "guild", None)
    me = getattr(guild, "me", None)
    permissions_for = getattr(channel, "permissions_for", None)
    if guild is None or me is None or permissions_for is None:
        return None

    permissions = permissions_for(me)
    if not getattr(permissions, "read_message_history", False):
        return "me falta el permiso Read Message History en este canal."
    if not getattr(permissions, "manage_messages", False):
        return "me falta el permiso Manage Messages en este canal."
    return None


if __name__ == "__main__":
    main()
