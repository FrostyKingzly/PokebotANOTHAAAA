
"""
Shop Cog - PokeMart with rank-aware access and modal quantity input.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands


class QuantityModal(discord.ui.Modal):
    """Modal to let the user type an exact purchase quantity."""

    def __init__(self, cog: "ShopCog", buyer_id: int, item_id: str):
        super().__init__(title="Choose quantity")
        self.cog = cog
        self.buyer_id = buyer_id
        self.item_id = item_id

        self.quantity_input = discord.ui.TextInput(
            label="Quantity",
            placeholder="Enter a positive number (e.g. 1, 10, 25)",
            required=True,
            max_length=6,
        )
        self.add_item(self.quantity_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Only the original buyer can submit
        if interaction.user.id != self.buyer_id:
            await interaction.response.send_message(
                "❌ This quantity prompt isn't for you.",
                ephemeral=True,
            )
            return

        # Parse quantity
        raw = str(self.quantity_input.value).strip()
        try:
            qty = int(raw)
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a whole number (like 1, 10, 25).",
                ephemeral=True,
            )
            return

        if qty <= 0:
            await interaction.response.send_message(
                "❌ Quantity must be at least 1.",
                ephemeral=True,
            )
            return

        await self.cog._handle_purchase(interaction, item_id=self.item_id, quantity=qty)


class ShopItemSelect(discord.ui.Select):
    """Dropdown selector for buying an item from the shop."""

    def __init__(
        self,
        cog: "ShopCog",
        shop_view: "ShopView",
        available_items: Dict[str, Dict[str, Any]],
    ):
        self.cog = cog
        self.shop_view = shop_view
        self.available_items = available_items

        options: List[discord.SelectOption] = []

        for item_id, meta in available_items.items():
            item_data = cog.bot.items_db.get_item(item_id) or {"name": item_id}
            name = cog._sanitize_text(item_data.get("name", item_id))
            price = int(meta.get("price", 0))

            desc = item_data.get("description") or ""
            short_desc = desc.split(". ")[0] if desc else ""
            short_desc = cog._sanitize_text(short_desc)

            if len(short_desc) > 80:
                short_desc = short_desc[:77] + "..."

            label = name[:100]
            description = f"${price:,}"
            if short_desc:
                description += f" — {short_desc}"
            description = description[:100]

            options.append(
                discord.SelectOption(
                    label=label,
                    description=description,
                    value=item_id,
                )
            )

        super().__init__(
            placeholder="Choose an item to buy…",
            min_values=1,
            max_values=1,
            options=options[:25],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.shop_view.buyer_id:
            await interaction.response.send_message(
                "❌ This isn't your shop menu.",
                ephemeral=True,
            )
            return

        item_id = self.values[0]
        modal = QuantityModal(self.cog, self.shop_view.buyer_id, item_id)
        await interaction.response.send_modal(modal)


class ShopView(discord.ui.View):
    """View containing the item selector."""

    def __init__(
        self,
        cog: "ShopCog",
        buyer_id: int,
        available_items: Dict[str, Dict[str, Any]],
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.buyer_id = buyer_id

        self.add_item(ShopItemSelect(cog, self, available_items))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.buyer_id


class ShopCog(commands.Cog, name="ShopCog"):
    """Handles PokeMart shops that scale with (future) league rank."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.shop_items: Dict[str, Dict[str, Any]] = {}
        self._load_shop_items()

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _load_shop_items(self) -> None:
        """Load shop configuration from data/shop_items.json."""
        path = Path("data/shop_items.json")
        if not path.exists():
            print("⚠️ shop_items.json not found, shops will be empty.")
            self.shop_items = {}
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.shop_items = data
            else:
                print("⚠️ shop_items.json must be an object mapping item_id -> metadata.")
                self.shop_items = {}
        except Exception as e:
            print(f"⚠️ Failed to load shop_items.json: {e}")
            self.shop_items = {}

    def _sanitize_text(self, text: str) -> str:
        """Fix cursed encoding / accents for Pokémon-related words."""
        if not text:
            return text
        cleaned = text
        replacements = {
            "POKÃ©MON": "Pokémon",
            "POKéMON": "Pokémon",
            "POKEMON": "Pokémon",
            "PokÃ©mon": "Pokémon",
            "PokÃ©": "Poké",
        }
        for bad, good in replacements.items():
            cleaned = cleaned.replace(bad, good)
        return cleaned

    def _get_player_rank_name_and_tier(self, discord_id: int) -> tuple[int, str]:
        """
        Simple rank helper.

        If a RankCog exists and exposes rank_tier_number / rank_tier_name,
        we use that. Otherwise we default to Tier 1 – Qualifiers.
        """
        trainer = self.bot.player_manager.get_player(discord_id)
        if not trainer:
            return 1, "Qualifiers"

        tier = getattr(trainer, "rank_tier_number", None) or 1
        try:
            tier = int(tier)
        except Exception:
            tier = 1
        if tier < 1:
            tier = 1

        name = getattr(trainer, "rank_tier_name", None) or "Qualifiers"
        return tier, str(name)

    def _location_has_pokemon_center(self, location_id: Optional[str]) -> bool:
        """Check whether the current location has a Pokemon Center amenity."""
        if not location_id:
            return False
        lm = getattr(self.bot, "location_manager", None)
        if not lm:
            return False
        try:
            return bool(lm.has_pokemon_center(location_id))
        except Exception:
            return False

    def _get_available_items_for_player(self, discord_id: int) -> Dict[str, Dict[str, Any]]:
        """
        For now: everyone can buy any item whose min_tier <= player's tier.
        Future: you can also gate based on global league unlocks.
        """
        player_tier, _ = self._get_player_rank_name_and_tier(discord_id)
        allowed: Dict[str, Dict[str, Any]] = {}
        for item_id, meta in self.shop_items.items():
            try:
                min_tier = int(meta.get("min_tier", 1))
            except Exception:
                min_tier = 1
            if min_tier <= player_tier:
                allowed[item_id] = meta
        return allowed

    # ------------------------------------------------------------
    # Public entrypoints
    # ------------------------------------------------------------

    async def open_shop_for_user(self, interaction: discord.Interaction) -> None:
        """Open the PokeMart for the user (used by menu button and /shop)."""
        pm = self.bot.player_manager

        if not pm.player_exists(interaction.user.id):
            await interaction.response.send_message(
                "❌ You haven't registered yet! Use `/register` first.",
                ephemeral=True,
            )
            return

        trainer = pm.get_player(interaction.user.id)
        location_id = getattr(trainer, "current_location_id", None)

        if not self._location_has_pokemon_center(location_id):
            await interaction.response.send_message(
                "🚫 There is no PokeMart at your current location.",
                ephemeral=True,
            )
            return

        available_items = self._get_available_items_for_player(interaction.user.id)
        if not available_items:
            await interaction.response.send_message(
                "🛒 The PokeMart doesn't have any items available yet.",
                ephemeral=True,
            )
            return

        # Location name
        lm = getattr(self.bot, "location_manager", None)
        if lm:
            loc_data = lm.get_location(location_id) or {}
            location_name = loc_data.get("name", location_id or "Unknown Location")
        else:
            location_name = location_id or "Unknown Location"

        location_name = self._sanitize_text(location_name)

        tier, rank_name = self._get_player_rank_name_and_tier(interaction.user.id)

        desc_lines = [
            f"Your Rank: **Tier {tier} – {rank_name}**",
            "",
            "Choose an item below and you'll be asked how many to buy.",
        ]

        embed = discord.Embed(
            title=f"{location_name} – PokeMart",
            description="\n".join(desc_lines),
            color=discord.Color.blue(),
        )

        # Build a single item-list field
        lines: List[str] = []
        for item_id, meta in available_items.items():
            item_data = self.bot.items_db.get_item(item_id) or {"name": item_id}
            name = self._sanitize_text(item_data.get("name", item_id))
            price = int(meta.get("price", 0))
            desc = item_data.get("description") or ""
            short_desc = desc.split(". ")[0] if desc else ""
            short_desc = self._sanitize_text(short_desc)
            if len(short_desc) > 80:
                short_desc = short_desc[:77] + "..."

            line = f"• **{name}** — ${price:,}"
            if short_desc:
                line += f" — {short_desc}"
            lines.append(line)

        if lines:
            embed.add_field(
                name="Available Items",
                value="\n".join(lines),
                inline=False,
            )

        embed.set_footer(text="Buying 10 or more of any Poké Ball in one purchase grants a free Premier Ball.")

        view = ShopView(
            cog=self,
            buyer_id=interaction.user.id,
            available_items=available_items,
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_purchase(
        self,
        interaction: discord.Interaction,
        item_id: str,
        quantity: int = 1,
    ) -> None:
        """Shared purchase logic for modal / commands."""
        if quantity <= 0:
            await interaction.response.send_message(
                "❌ Quantity must be at least 1.",
                ephemeral=True,
            )
            return

        pm = self.bot.player_manager

        if not pm.player_exists(interaction.user.id):
            await interaction.response.send_message(
                "❌ You haven't registered yet! Use `/register` first.",
                ephemeral=True,
            )
            return

        trainer = pm.get_player(interaction.user.id)
        location_id = getattr(trainer, "current_location_id", None)

        if not self._location_has_pokemon_center(location_id):
            await interaction.response.send_message(
                "🚫 There is no PokeMart at your current location.",
                ephemeral=True,
            )
            return

        available_items = self._get_available_items_for_player(interaction.user.id)
        if item_id not in available_items:
            await interaction.response.send_message(
                "❌ That item is not available in this PokeMart.",
                ephemeral=True,
            )
            return

        meta = available_items[item_id]
        price = int(meta.get("price", 0))
        total_cost = price * quantity

        current_money = getattr(trainer, "money", 0)
        if total_cost > current_money:
            await interaction.response.send_message(
                f"💸 You don't have enough money! You need **${total_cost:,}**, "
                f"but you only have **${current_money:,}**.",
                ephemeral=True,
            )
            return

        item_data = self.bot.items_db.get_item(item_id)
        if not item_data:
            await interaction.response.send_message(
                f"❌ The item `{item_id}` doesn't exist in items.json. Contact an admin.",
                ephemeral=True,
            )
            return

        # Deduct money and add items
        new_balance = current_money - total_cost
        pm.update_player(interaction.user.id, money=new_balance)
        pm.add_item(interaction.user.id, item_id, quantity)

        # Premier Ball bonus: 1 per 10 non-Premier Poké Balls bought
        bonus_premier = 0
        premier_id = "premier_ball"
        if item_id.endswith("ball") and item_id != premier_id:
            bonus_premier = quantity // 10
            if bonus_premier > 0 and self.bot.items_db.get_item(premier_id):
                pm.add_item(interaction.user.id, premier_id, bonus_premier)

        display_name = self._sanitize_text(item_data.get("name", item_id))

        desc = f"You bought **{quantity}x {display_name}** for **${total_cost:,}**."
        if bonus_premier > 0:
            desc += f"\nYou also received **{bonus_premier}x Premier Ball** as a bonus!"

        embed = discord.Embed(
            title="🛒 Purchase Complete!",
            description=desc,
            color=discord.Color.green(),
        )
        embed.add_field(
            name="New Balance",
            value=f"${new_balance:,}",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------
    # Optional slash commands
    # ------------------------------------------------------------

    @app_commands.command(name="shop", description="View the PokeMart for your current location.")
    async def shop(self, interaction: discord.Interaction) -> None:
        await self.open_shop_for_user(interaction)

    @app_commands.command(name="buy", description="Buy an item from the local PokeMart.")
    @app_commands.describe(
        item="Item ID or name (e.g., 'potion', 'poke_ball')",
        quantity="How many to buy (default: 1)",
    )
    async def buy(self, interaction: discord.Interaction, item: str, quantity: int = 1) -> None:
        item_id = item.lower().replace(" ", "_")
        await self._handle_purchase(interaction, item_id=item_id, quantity=quantity)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCog(bot))
