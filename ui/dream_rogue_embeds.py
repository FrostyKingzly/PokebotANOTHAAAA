"""
Dream Dive Embed Builders

Provides formatted Discord embeds for the Dream Dive gamemode
"""

import discord
from typing import List, Dict, Optional


class DreamRogueEmbeds:
    """Static methods for building Dream Dive embeds"""

    # Colors
    DREAM_COLOR = discord.Color.from_rgb(138, 43, 226)  # Blue-Violet
    NIGHTMARE_COLOR = discord.Color.from_rgb(75, 0, 130)  # Indigo
    SUCCESS_COLOR = discord.Color.green()
    DANGER_COLOR = discord.Color.red()
    WARNING_COLOR = discord.Color.orange()
    INFO_COLOR = discord.Color.blue()

    # Emojis
    DREAMLITE_EMOJI = "💎"
    FLOOR_EMOJI = "🌀"
    BATTLE_EMOJI = "⚔️"
    BUFF_EMOJI = "✨"
    CURSE_EMOJI = "😈"
    DOMAIN_EMOJI = "🌌"
    NIGHTMARE_EMOJI = "👁️"
    REWARD_EMOJI = "🎁"
    REST_EMOJI = "🛌"
    BOSS_EMOJI = "👑"
    VOTE_EMOJI = "🗳️"
    EXTRACT_EMOJI = "🚪"

    @staticmethod
    def run_status(run: Dict, participants: List[Dict], floor_level_range: tuple) -> discord.Embed:
        """
        Main run status embed

        Args:
            run: Run dict from database
            participants: List of participant dicts
            floor_level_range: (min_level, max_level) for current floor
        """
        floor = run["current_floor"]
        intensity = run.get("intensity", run.get("stage_level", 1))
        layer_name = run.get("layer_name", "Somnia Prima")

        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.FLOOR_EMOJI} Dream Dive — {layer_name}",
            description="*Now Diving… Please Stand By.*",
            color=DreamRogueEmbeds.DREAM_COLOR
        )

        # Floor info
        min_lvl, max_lvl = floor_level_range
        embed.add_field(
            name="Dive Information",
            value=(
                f"**Layer:** {layer_name}\n"
                f"**Intensity:** {intensity}\n"
                f"**Floor:** {floor}/10\n"
                f"**Enemy Level Range:** {min_lvl}-{max_lvl}"
            ),
            inline=False
        )

        # Participants
        participant_lines = []
        for p in participants:
            dreamlites = p["dreamlites"]
            participant_lines.append(f"<@{p['discord_user_id']}>: {DreamRogueEmbeds.DREAMLITE_EMOJI} {dreamlites}")

        embed.add_field(
            name=f"Team ({len(participants)})",
            value="\n".join(participant_lines) if participant_lines else "*No participants*",
            inline=False
        )

        embed.set_footer(text="Use the buttons below to navigate instances")
        return embed

    @staticmethod
    def node_selection(current_node: Dict, next_nodes: List[Dict], layer_name: str, intensity: int) -> discord.Embed:
        """Embed for selecting the next node in the map."""
        def _node_display(node: Dict) -> str:
            node_type = node.get("node_type", "event")
            emoji_map = {
                "combat": DreamRogueEmbeds.BATTLE_EMOJI,
                "event": "❓",
                "rest": "🔥",
                "mini_boss": "🟣",
                "boss": DreamRogueEmbeds.BOSS_EMOJI,
            }
            label_map = {
                "combat": "Combat Encounter",
                "event": "Dream Event",
                "rest": "Rest Area",
                "mini_boss": "Mini Boss",
                "boss": "Floor Boss",
            }
            emoji = emoji_map.get(node_type, "❓")
            label = label_map.get(node_type, "Unknown")
            shop = " 🛍️" if node.get("has_shop") else ""
            return f"{emoji} **{label}**{shop}"

        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.FLOOR_EMOJI} Choose the Next Node",
            description=(
                f"*Layer {layer_name} — Intensity {intensity} — "
                f"Current Depth {current_node.get('depth', 1)}*"
            ),
            color=DreamRogueEmbeds.DREAM_COLOR
        )

        for idx, node in enumerate(next_nodes, start=1):
            embed.add_field(
                name=f"Option {idx}",
                value=_node_display(node),
                inline=False
            )

        embed.set_footer(text="Team vote decides the path forward.")
        return embed

    @staticmethod
    def instance_selection(instance: Dict, stage: int) -> discord.Embed:
        """
        Instance encounter embed

        Args:
            instance: Instance dict from template
            floor: Current floor number
        """
        name = instance.get("name", "Unknown Instance")
        description = instance.get("description", "")
        categories = instance.get("categories", [])
        scope = instance.get("scope", "team")
        risk_level = instance.get("risk_level", "medium")

        # Choose color based on category
        if "nightmare" in categories or "curse" in categories:
            color = DreamRogueEmbeds.NIGHTMARE_COLOR
            emoji = DreamRogueEmbeds.NIGHTMARE_EMOJI
        elif "domain" in categories:
            color = DreamRogueEmbeds.DREAM_COLOR
            emoji = DreamRogueEmbeds.DOMAIN_EMOJI
        elif "mini_boss" in categories:
            color = DreamRogueEmbeds.WARNING_COLOR
            emoji = "🟣"
        elif "battle" in categories or "boss" in categories:
            color = DreamRogueEmbeds.DANGER_COLOR
            emoji = DreamRogueEmbeds.BOSS_EMOJI if "boss" in categories else DreamRogueEmbeds.BATTLE_EMOJI
        elif "event" in categories:
            color = DreamRogueEmbeds.INFO_COLOR
            emoji = "❓"
        elif "buff" in categories:
            color = DreamRogueEmbeds.SUCCESS_COLOR
            emoji = DreamRogueEmbeds.BUFF_EMOJI
        elif "rest" in categories:
            color = DreamRogueEmbeds.INFO_COLOR
            emoji = DreamRogueEmbeds.REST_EMOJI
        elif "reward" in categories or "economy" in categories:
            color = DreamRogueEmbeds.WARNING_COLOR
            emoji = DreamRogueEmbeds.REWARD_EMOJI
        else:
            color = DreamRogueEmbeds.INFO_COLOR
            emoji = "❓"

        embed = discord.Embed(
            title=f"{emoji} {name}",
            description=description,
            color=color
        )

        # Instance details
        details = []
        details.append(f"**Scope:** {scope.title()}")
        details.append(f"**Risk:** {risk_level.title()}")

        # Cost info
        dreamlite_cost = instance.get("dreamlite_cost", 0)
        if dreamlite_cost > 0:
            details.append(f"**Cost:** {DreamRogueEmbeds.DREAMLITE_EMOJI} {dreamlite_cost}")

        star_required = instance.get("star_stat_required")
        if star_required:
            threshold = instance.get("star_stat_threshold", 1)
            details.append(f"**Requires:** {star_required.title()} {threshold}+")

        embed.add_field(
            name="Details",
            value="\n".join(details),
            inline=False
        )

        # Categories
        embed.add_field(
            name="Tags",
            value=" • ".join(f"`{cat}`" for cat in categories),
            inline=False
        )

        embed.set_footer(text=f"Stage {stage}")
        return embed

    @staticmethod
    def voting(vote: Dict, percentages: Dict[int, float]) -> discord.Embed:
        """
        Voting status embed

        Args:
            vote: Vote dict from database
            percentages: Dict mapping option_index -> percentage
        """
        prompt = vote["vote_prompt"]
        options = vote["vote_options"]
        votes = vote["votes"]

        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.VOTE_EMOJI} Team Vote",
            description=prompt,
            color=DreamRogueEmbeds.DREAM_COLOR
        )

        # Show each option with vote percentage
        for idx, option in enumerate(options):
            option_name = option.get("name", f"Option {idx + 1}")
            option_desc = option.get("description", "")

            percent = percentages.get(idx, 0)
            vote_count = sum(1 for v in votes.values() if v == idx)

            # Visual bar
            bar_length = 10
            filled = int((percent / 100) * bar_length)
            bar = "█" * filled + "░" * (bar_length - filled)

            value = f"{option_desc}\n{bar} **{percent:.1f}%** ({vote_count} votes)"

            embed.add_field(
                name=f"{idx + 1}. {option_name}",
                value=value,
                inline=False
            )

        total_votes = len(votes)
        embed.set_footer(text=f"{total_votes} total votes • Each vote = equal weight")
        return embed

    @staticmethod
    def vote_result(vote: Dict, result_index: int) -> discord.Embed:
        """
        Vote resolution embed

        Args:
            vote: Vote dict
            result_index: Winning option index
        """
        options = vote["vote_options"]
        winning_option = options[result_index]

        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.VOTE_EMOJI} Vote Resolved!",
            description=f"**{winning_option['name']}** has been chosen!",
            color=DreamRogueEmbeds.SUCCESS_COLOR
        )

        embed.add_field(
            name="Effect",
            value=winning_option.get("description", "The dream shifts..."),
            inline=False
        )

        return embed

    @staticmethod
    def battle_reward(
        victory: bool,
        dreamlites_gained: int,
        exp_gained: int,
        buffs_applied: List[Dict[str, str]] = None
    ) -> discord.Embed:
        """
        Battle completion reward embed

        Args:
            victory: Whether battle was won
            dreamlites_gained: Dreamlites earned (can be negative for loss)
            exp_gained: Experience earned
            buffs_applied: List of buff names applied
        """
        if victory:
            embed = discord.Embed(
                title=f"{DreamRogueEmbeds.BATTLE_EMOJI} Victory!",
                description="The dream yields to your strength.",
                color=DreamRogueEmbeds.SUCCESS_COLOR
            )
        else:
            embed = discord.Embed(
                title=f"{DreamRogueEmbeds.BATTLE_EMOJI} Defeat",
                description="The nightmare grows stronger...",
                color=DreamRogueEmbeds.DANGER_COLOR
            )

        rewards = []
        if dreamlites_gained != 0:
            if dreamlites_gained > 0:
                rewards.append(f"+ {DreamRogueEmbeds.DREAMLITE_EMOJI} **{dreamlites_gained}** Dreamlites")
            else:
                rewards.append(f"- {DreamRogueEmbeds.DREAMLITE_EMOJI} **{abs(dreamlites_gained)}** Dreamlites")

        if exp_gained > 0:
            rewards.append(f"+ **{exp_gained}** EXP")

        if buffs_applied:
            for buff in buffs_applied:
                name = buff.get("name", "Dream Blessing")
                description = buff.get("description", "A gentle boon from the dream.")
                rewards.append(f"{DreamRogueEmbeds.BUFF_EMOJI} **{name}** — {description}")

        if rewards:
            embed.add_field(
                name="Rewards" if victory else "Consequences",
                value="\n".join(rewards),
                inline=False
            )

        return embed

    @staticmethod
    def safe_room() -> discord.Embed:
        """Safe room / rest area embed"""
        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.REST_EMOJI} Safe Room",
            description="*A moment of clarity in the endless dream.*\n\nYour Pokémon can rest here. You may also extract and return later.",
            color=DreamRogueEmbeds.INFO_COLOR
        )

        embed.add_field(
            name="Options",
            value=(
                f"{DreamRogueEmbeds.REST_EMOJI} **Rest** — Restore HP and PP\n"
                f"{DreamRogueEmbeds.EXTRACT_EMOJI} **Extract** — Save and leave the dream\n"
                f"{DreamRogueEmbeds.FLOOR_EMOJI} **Continue** — Press onward"
            ),
            inline=False
        )

        return embed

    @staticmethod
    def extraction_summary(
        run: Dict,
        participants: List[Dict],
        floor_reached: int,
        total_dreamlites: int,
        exp_rewards: Optional[Dict[int, int]] = None
    ) -> discord.Embed:
        """
        Extraction completion summary

        Args:
            run: Run dict
            participants: Participant dicts
            floor_reached: Highest floor reached
            total_dreamlites: Total Dreamlites earned across team
        """
        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.EXTRACT_EMOJI} Extraction Complete",
            description="*You awaken from the dream, treasures in hand.*",
            color=DreamRogueEmbeds.SUCCESS_COLOR
        )

        embed.add_field(
            name="Run Statistics",
            value=(
                f"**Starting Floor:** {run['starting_floor']}\n"
                f"**Final Floor:** {floor_reached}\n"
                f"**Floors Cleared:** {floor_reached - run['starting_floor'] + 1}"
            ),
            inline=False
        )

        # Individual rewards
        participant_rewards = []
        for p in participants:
            dreamlites = p["dreamlites"]
            participant_rewards.append(f"<@{p['discord_user_id']}>: {DreamRogueEmbeds.DREAMLITE_EMOJI} {dreamlites}")

        embed.add_field(
            name="Dreamlites Earned",
            value="\n".join(participant_rewards),
            inline=False
        )

        embed.add_field(
            name="Total",
            value=f"{DreamRogueEmbeds.DREAMLITE_EMOJI} **{total_dreamlites}** Dreamlites",
            inline=False
        )

        if exp_rewards:
            reward_lines = []
            for participant in participants:
                user_id = participant["discord_user_id"]
                reward = exp_rewards.get(user_id)
                if reward is None:
                    continue
                reward_lines.append(f"<@{user_id}>: **{reward:,}** EXP")

            if reward_lines:
                embed.add_field(
                    name="Dream Dive EXP",
                    value="\n".join(reward_lines),
                    inline=False
                )

        embed.set_footer(text="Dreamlites have been added to your collection")
        return embed

    @staticmethod
    def active_buffs(buffs: List[Dict], user_name: str = None) -> discord.Embed:
        """
        Display active buffs/curses

        Args:
            buffs: List of buff dicts
            user_name: Optional user name for individual buffs
        """
        title = f"{DreamRogueEmbeds.BUFF_EMOJI} Active Effects"
        if user_name:
            title += f" — {user_name}"

        embed = discord.Embed(
            title=title,
            description="*These forces shape your journey through the dream.*",
            color=DreamRogueEmbeds.DREAM_COLOR
        )

        if not buffs:
            embed.description = "*No active effects.*"
            return embed

        # Group by type
        team_buffs = [b for b in buffs if b["scope"] == "team"]
        individual_buffs = [b for b in buffs if b["scope"] == "individual"]

        if team_buffs:
            lines = []
            for buff in team_buffs:
                emoji = DreamRogueEmbeds._get_buff_emoji(buff["buff_type"])
                name = buff["buff_name"]
                duration = buff["duration"]

                duration_text = ""
                if buff.get("battles_remaining"):
                    duration_text = f" ({buff['battles_remaining']} battles)"
                elif buff.get("floors_remaining"):
                    duration_text = f" ({buff['floors_remaining']} floors)"
                elif duration != "permanent":
                    duration_text = f" ({duration})"

                description = buff.get("buff_description", "")
                line = f"{emoji} **{name}**{duration_text}"
                if description:
                    line = f"{line}\n{description}"
                lines.append(line)

            embed.add_field(
                name="Team Effects",
                value="\n".join(lines),
                inline=False
            )

        if individual_buffs and user_name:
            lines = []
            for buff in individual_buffs:
                emoji = DreamRogueEmbeds._get_buff_emoji(buff["buff_type"])
                name = buff["buff_name"]
                duration = buff["duration"]

                duration_text = ""
                if buff.get("battles_remaining"):
                    duration_text = f" ({buff['battles_remaining']} battles)"
                elif buff.get("floors_remaining"):
                    duration_text = f" ({buff['floors_remaining']} floors)"
                elif duration != "permanent":
                    duration_text = f" ({duration})"

                description = buff.get("buff_description", "")
                line = f"{emoji} **{name}**{duration_text}"
                if description:
                    line = f"{line}\n{description}"
                lines.append(line)

            embed.add_field(
                name="Your Effects",
                value="\n".join(lines),
                inline=False
            )

        return embed

    @staticmethod
    def _get_buff_emoji(buff_type: str) -> str:
        """Get emoji for buff type"""
        if buff_type == "buff":
            return DreamRogueEmbeds.BUFF_EMOJI
        elif buff_type == "curse":
            return DreamRogueEmbeds.CURSE_EMOJI
        elif buff_type == "domain":
            return DreamRogueEmbeds.DOMAIN_EMOJI
        elif buff_type == "nightmare":
            return DreamRogueEmbeds.NIGHTMARE_EMOJI
        else:
            return "🔮"

    @staticmethod
    def shop(available_buffs: List[Dict], user_dreamlites: int) -> discord.Embed:
        """
        Shop embed for purchasing buffs

        Args:
            available_buffs: List of purchasable buff dicts
            user_dreamlites: User's current Dreamlites
        """
        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.REWARD_EMOJI} Dream Shop",
            description=f"*Exchange Dreamlites for power.*\n\nYour Dreamlites: {DreamRogueEmbeds.DREAMLITE_EMOJI} **{user_dreamlites}**",
            color=DreamRogueEmbeds.WARNING_COLOR
        )

        if not available_buffs:
            embed.description += "\n\n*No items available.*"
            return embed

        for buff in available_buffs[:10]:  # Limit to 10
            name = buff.get("name", "Unknown")
            cost = buff.get("dreamlite_cost", 0)
            description = buff.get("description", "")

            can_afford = user_dreamlites >= cost
            status = "✅" if can_afford else "❌"

            embed.add_field(
                name=f"{status} {name} — {DreamRogueEmbeds.DREAMLITE_EMOJI} {cost}",
                value=description,
                inline=False
            )

        return embed

    @staticmethod
    def floor_complete(floor: int, next_floor: int) -> discord.Embed:
        """Floor completion embed"""
        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.FLOOR_EMOJI} Floor {floor} Complete!",
            description=f"*The dream deepens...*\n\nPrepare for **Floor {next_floor}**",
            color=DreamRogueEmbeds.SUCCESS_COLOR
        )

        if next_floor == 10:
            embed.description += "\n\n⚠️ **Boss Floor Ahead** ⚠️"
            embed.color = DreamRogueEmbeds.WARNING_COLOR

        return embed

    @staticmethod
    def stage_travel(current_stage: int, next_stage: int) -> discord.Embed:
        """Stage transition embed"""
        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.FLOOR_EMOJI} Traversing the Dream World",
            description=f"*Traveling to Stage {next_stage}...*\n\nStage {current_stage} fades into the mist.",
            color=DreamRogueEmbeds.INFO_COLOR
        )
        embed.set_footer(text="Hold tight...")
        return embed

    @staticmethod
    def stage_intro(stage: int) -> discord.Embed:
        """Stage arrival embed"""
        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.FLOOR_EMOJI} Arrived at Stage {stage}",
            description="*The dream shifts around you.*",
            color=DreamRogueEmbeds.DREAM_COLOR
        )
        return embed

    @staticmethod
    def boss_intro(floor: int) -> discord.Embed:
        """Boss battle introduction"""
        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.BOSS_EMOJI} Floor {floor} Guardian",
            description="*A powerful presence stirs in the depths of the dream.*\n\nPrepare for a raid battle against the floor guardian!",
            color=DreamRogueEmbeds.DANGER_COLOR
        )

        embed.add_field(
            name="⚠️ Warning",
            value="This is a raid battle. All participants will fight together against a single powerful foe.",
            inline=False
        )

        return embed

    @staticmethod
    def dive_start(layer_name: str, intensity: int, participants: List[int]) -> discord.Embed:
        """Initial dive embed"""
        embed = discord.Embed(
            title=f"{DreamRogueEmbeds.FLOOR_EMOJI} Diving into the Dream...",
            description="*Reality fades. The dream world beckons.*",
            color=DreamRogueEmbeds.DREAM_COLOR
        )

        embed.add_field(
            name="Dive Details",
            value=(
                f"**Layer:** {layer_name}\n"
                f"**Intensity:** {intensity}\n"
                f"**Participants:** {len(participants)}\n"
                f"**Starting Floor:** 1/10"
            ),
            inline=False
        )

        embed.add_field(
            name="Remember",
            value=(
                f"{DreamRogueEmbeds.DREAMLITE_EMOJI} Earn Dreamlites through victory\n"
                f"{DreamRogueEmbeds.REST_EMOJI} Safe rooms allow rest and extraction\n"
                f"{DreamRogueEmbeds.VOTE_EMOJI} Team votes use weighted random selection"
            ),
            inline=False
        )

        embed.set_footer(text="Good luck, dreamers.")
        return embed
