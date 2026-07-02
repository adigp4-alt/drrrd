"""Discord bot — bidirectional commands and alert delivery."""

import asyncio
import logging
import os
import threading

import discord
from discord.ext import commands

from app.data_fetcher import CACHE, fetch_prices
from app.models import execute_db, query_db

logger = logging.getLogger(__name__)

# Global bot instance so send_discord() can reach it
_bot = None


def send_discord(message):
    """Send a message to DISCORD_CHANNEL_ID from synchronous code (e.g. scheduler)."""
    if _bot is None or not _bot.is_ready():
        return False
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    if not channel_id:
        return False
    try:
        channel = _bot.get_channel(int(channel_id))
        if channel is None:
            return False
        asyncio.run_coroutine_threadsafe(channel.send(message), _bot.loop)
        return True
    except Exception as exc:
        logger.error("Discord send error: %s", exc)
        return False


def _make_bot():
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    @bot.event
    async def on_ready():
        logger.info("Discord bot logged in as %s", bot.user)

    @bot.command(name="help")
    async def cmd_help(ctx):
        await ctx.send(
            "**Remote Control Commands:**\n"
            "`!prices [TICKER]` — All prices or a specific ticker\n"
            "`!portfolio` — Portfolio P&L summary\n"
            "`!refresh` — Force price refresh\n"
            "`!alerts` — List active alert rules\n"
            "`!add TICKER SHARES PRICE` — Add a holding"
        )

    @bot.command(name="prices")
    async def cmd_prices(ctx, ticker: str = None):
        data = CACHE.get("data", {})
        if not data:
            await ctx.send("No price data available yet.")
            return
        if ticker:
            sym = ticker.upper()
            d = data.get(sym)
            if not d:
                await ctx.send(f"{sym} not found.")
                return
            await ctx.send(f"**{sym}**: ${d['price']:.2f} ({d['change_pct']:+.2f}%)")
            return
        lines = [
            f"**{s}**: ${d['price']:.2f} ({d['change_pct']:+.2f}%)"
            for s, d in list(data.items())[:20]
        ]
        ts = CACHE.get("last_updated", "unknown")
        await ctx.send("\n".join(lines) + f"\n_Updated: {ts}_")

    @bot.command(name="portfolio")
    async def cmd_portfolio(ctx):
        holdings = query_db("SELECT * FROM holdings")
        if not holdings:
            await ctx.send("No holdings in portfolio.")
            return
        current = CACHE.get("data", {})
        total_mv = total_pnl = 0.0
        lines = []
        for h in holdings:
            price = current.get(h["ticker"], {}).get("price", h["buy_price"])
            mv = h["shares"] * price
            pnl = mv - h["shares"] * h["buy_price"]
            total_mv += mv
            total_pnl += pnl
            lines.append(f"**{h['ticker']}**: ${mv:,.0f} (PnL: {pnl:+,.0f})")
        lines.append(f"\n**Total**: ${total_mv:,.0f} | **PnL**: {total_pnl:+,.0f}")
        await ctx.send("\n".join(lines))

    @bot.command(name="refresh")
    async def cmd_refresh(ctx):
        fetch_prices()
        await ctx.send(f"Refreshed. Last updated: {CACHE.get('last_updated', 'unknown')}")

    @bot.command(name="alerts")
    async def cmd_alerts(ctx):
        rules = query_db("SELECT * FROM alert_rules WHERE enabled = 1")
        if not rules:
            await ctx.send("No active alert rules.")
            return
        await ctx.send("\n".join(
            f"{r['ticker']} {r['condition']} {r['threshold']}" for r in rules
        ))

    @bot.command(name="add")
    async def cmd_add(ctx, ticker: str = None, shares: str = None, price: str = None):
        if not ticker or not shares or not price:
            await ctx.send("Usage: `!add TICKER SHARES PRICE`")
            return
        try:
            shares_f = float(shares)
            price_f = float(price)
        except ValueError:
            await ctx.send("Invalid format. Usage: `!add TICKER SHARES PRICE`")
            return
        execute_db(
            "INSERT INTO holdings (ticker, shares, buy_price) VALUES (?, ?, ?)",
            (ticker.upper(), shares_f, price_f),
        )
        await ctx.send(f"Added {shares_f} shares of {ticker.upper()} at ${price_f:.2f}")

    return bot


def start_bot():
    global _bot
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        return
    _bot = _make_bot()

    def _run():
        _bot.run(token, log_handler=None)

    threading.Thread(target=_run, name="discord-bot", daemon=True).start()
    logger.info("Discord bot thread started")
