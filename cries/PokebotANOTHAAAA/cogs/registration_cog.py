"""Registration Cog - Handles /register command and new trainer setup"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, View, Button, Select

from ui.embeds import EmbedBuilder
from social_stats import SOCIAL_STAT_DEFINITIONS


def get_stat_display_name(stat_key: str) -> str:
    """Return the display name for a stat key, falling back to title-casing."""

    definition = SOCIAL_STAT_DEFINITIONS.get(stat_key)
    return definition.display_name if definition else stat_key.title()


# Registration step constants
REGIONS = [
    "Kanto", "Johto", "Hoenn", "Sinnoh", "Unova",
    "Kalos", "Alola", "Galar", "Paldea", "Other"
]


class RegistrationData:
    """Storage for registration data during the flow"""
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.trainer_name = None
        self.pronouns = None
        self.age = None
        self.birthday = None
        self.home_region = None
        self.bio = None
        self.boon_stat = None
        self.bane_stat = None
        self.avatar_url = None


# Step 1: Name Input
class NameModal(Modal, title="Your Name"):
    trainer_name = discord.ui.TextInput(
        label="First Name",
        placeholder="Enter your character's first name...",
        required=True,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        reg_data = interaction.client.temp_registration_data
        reg_data.trainer_name = self.trainer_name.value.strip()

        embed = discord.Embed(
            title="📝 Registration Center",
            description=(
                f"\"**{reg_data.trainer_name}**... That's a lovely name!\"\n\n"
                "\"And what are your pronouns?\""
            ),
            color=discord.Color.blue()
        )

        view = PronounsStepView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# Step 2: Pronouns Input
class PronounsModal(Modal, title="Your Pronouns"):
    pronouns = discord.ui.TextInput(
        label="Pronouns",
        placeholder="e.g., he/him, she/her, they/them, etc.",
        required=True,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        reg_data = interaction.client.temp_registration_data
        reg_data.pronouns = self.pronouns.value.strip()

        embed = discord.Embed(
            title="📝 Registration Center",
            description=(
                f"\"**{reg_data.pronouns}**... Got it!\"\n\n"
                "\"Perfect! And how old are you?\""
            ),
            color=discord.Color.blue()
        )

        view = AgeStepView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class PronounsStepView(View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: Button):
        modal = PronounsModal()
        await interaction.response.send_modal(modal)


# Step 3: Age Input
class AgeModal(Modal, title="Your Age"):
    age = discord.ui.TextInput(
        label="Age",
        placeholder="Enter your age in numbers...",
        required=True,
        max_length=3,
    )

    async def on_submit(self, interaction: discord.Interaction):
        reg_data = interaction.client.temp_registration_data
        reg_data.age = self.age.value.strip()

        embed = discord.Embed(
            title="📝 Registration Center",
            description=(
                f"\"**{reg_data.age}** years old, wonderful!\"\n\n"
                "\"Your birthday is...?\""
            ),
            color=discord.Color.blue()
        )

        view = BirthdayStepView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class AgeStepView(View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: Button):
        modal = AgeModal()
        await interaction.response.send_modal(modal)


# Step 3: Birthday Input
class BirthdayModal(Modal, title="Your Birthday"):
    birthday = discord.ui.TextInput(
        label="Birthday (MM/DD)",
        placeholder="Example: 04/20 or 12/25",
        required=True,
        max_length=5,
    )

    async def on_submit(self, interaction: discord.Interaction):
        reg_data = interaction.client.temp_registration_data
        reg_data.birthday = self.birthday.value.strip()

        embed = discord.Embed(
            title="📝 Registration Center",
            description=(
                f"\"**{reg_data.birthday}**... Got it!\"\n\n"
                "\"Right! Now, what's your home region?\""
            ),
            color=discord.Color.blue()
        )

        view = RegionSelectView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BirthdayStepView(View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: Button):
        modal = BirthdayModal()
        await interaction.response.send_modal(modal)


# Step 4: Region Selection
class RegionSelectView(View):
    def __init__(self):
        super().__init__(timeout=300)

        options = [
            discord.SelectOption(label=region, value=region.lower())
            for region in REGIONS
        ]

        select = Select(
            placeholder="Choose your home region...",
            options=options,
            custom_id="region_select"
        )
        select.callback = self.region_callback
        self.add_item(select)

    async def region_callback(self, interaction: discord.Interaction):
        reg_data = interaction.client.temp_registration_data
        reg_data.home_region = interaction.data['values'][0]

        embed = discord.Embed(
            title="📝 Registration Center",
            description=(
                f"\"**{reg_data.home_region.title()}**! A beautiful place!\"\n\n"
                "\"Great! Lastly, could you tell me a little bit about yourself?\"\n"
                "\"This part is optional — you can skip it if you'd like.\""
            ),
            color=discord.Color.blue()
        )

        view = BioStepView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# Step 5: Bio Input (Optional)
class BioModal(Modal, title="About You"):
    bio = discord.ui.TextInput(
        label="Tell us about yourself",
        placeholder="Write a small blurb about your trainer...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=250,
    )

    async def on_submit(self, interaction: discord.Interaction):
        reg_data = interaction.client.temp_registration_data
        reg_data.bio = self.bio.value.strip() if self.bio.value else None
        await self.show_social_stats(interaction)

    async def show_social_stats(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="✨ Choose Your Star Traits",
            description=(
                "\"Alright! Now let's determine your strengths and weaknesses.\"\n\n"
                "Every trainer has 5 Star Traits:\n\n"
                "**Heart** - Empathy & connection\n"
                "**Insight** - Perception & intellect\n"
                "**Charisma** - Charm & influence\n"
                "**Fortitude** - Strength & willpower\n"
                "**Clarity** - Focus & discipline\n\n"
                "Choose one **Boon** (Rank 2) and one **Bane** (Rank 0).\n"
                "The other three will start at Rank 1."
            ),
            color=discord.Color.blue(),
        )

        view = SocialStatsView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BioStepView(View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Write Bio", style=discord.ButtonStyle.primary)
    async def bio_button(self, interaction: discord.Interaction, button: Button):
        modal = BioModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        reg_data = interaction.client.temp_registration_data
        reg_data.bio = None

        embed = discord.Embed(
            title="✨ Choose Your Star Traits",
            description=(
                "\"Alright! Now let's determine your strengths and weaknesses.\"\n\n"
                "Every trainer has 5 Star Traits:\n\n"
                "**Heart** - Empathy & connection\n"
                "**Insight** - Perception & intellect\n"
                "**Charisma** - Charm & influence\n"
                "**Fortitude** - Strength & willpower\n"
                "**Clarity** - Focus & discipline\n\n"
                "Choose one **Boon** (Rank 2) and one **Bane** (Rank 0).\n"
                "The other three will start at Rank 1."
            ),
            color=discord.Color.blue(),
        )

        view = SocialStatsView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# Step 6: Star Traits Selection
class SocialStatsView(View):
    """Star Traits boon/bane selection"""

    def __init__(self):
        super().__init__(timeout=300)
        self.boon_stat = None
        self.bane_stat = None

        # Add boon select
        boon_options = [
            discord.SelectOption(label="Heart", value="heart",
                               description="Empathy & connection for people and Pokémon"),
            discord.SelectOption(label="Insight", value="insight",
                               description="Perception, research, and tactical thinking"),
            discord.SelectOption(label="Charisma", value="charisma",
                               description="Charm, influence, and negotiations"),
            discord.SelectOption(label="Fortitude", value="fortitude",
                               description="Strength, travel, and athletic feats"),
            discord.SelectOption(label="Clarity", value="will",
                               description="Focus, discipline, and resilience"),
        ]

        boon_select = Select(
            placeholder="Choose your BOON stat (Rank 2)...",
            options=boon_options,
            custom_id="boon_select"
        )
        boon_select.callback = self.boon_callback
        self.add_item(boon_select)

        # Add bane select
        bane_select = Select(
            placeholder="Choose your BANE stat (Rank 0)...",
            options=boon_options,
            custom_id="bane_select"
        )
        bane_select.callback = self.bane_callback
        self.add_item(bane_select)

    async def boon_callback(self, interaction: discord.Interaction):
        """Handle boon selection"""
        self.boon_stat = interaction.data['values'][0]
        reg_data = interaction.client.temp_registration_data
        reg_data.boon_stat = self.boon_stat

        await interaction.response.send_message(
            f"✔ **{get_stat_display_name(self.boon_stat)}** will be your strength! (Rank 2)",
            ephemeral=True
        )

        # Check if both selections are complete
        if self.boon_stat and self.bane_stat:
            await self.show_summary(interaction)

    async def bane_callback(self, interaction: discord.Interaction):
        """Handle bane selection"""
        self.bane_stat = interaction.data['values'][0]

        if self.boon_stat == self.bane_stat:
            await interaction.response.send_message(
                "❌ You cannot choose the same stat as both Boon and Bane!",
                ephemeral=True
            )
            self.bane_stat = None
            return

        reg_data = interaction.client.temp_registration_data
        reg_data.bane_stat = self.bane_stat

        await interaction.response.send_message(
            f"✔ **{get_stat_display_name(self.bane_stat)}** will be your weakness. (Rank 0)\n\n"
            f"Moving to confirmation...",
            ephemeral=True
        )

        # Check if both selections are complete
        if self.boon_stat and self.bane_stat:
            await self.show_avatar_prompt(interaction)

    async def show_avatar_prompt(self, interaction: discord.Interaction):
        """Prompt for avatar/photo URL"""
        embed = discord.Embed(
            title="📸 Character Photo",
            description=(
                "\"Lastly, would you like to submit a photo for your ID?\"\n\n"
                "You can provide an image URL, or skip this step."
            ),
            color=discord.Color.blue(),
        )

        view = AvatarStepView()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


# Avatar/Photo Step
class AvatarModal(Modal, title="Character Photo"):
    avatar_url = discord.ui.TextInput(
        label="Character Photo URL (optional)",
        placeholder="Paste a link to an image of your character...",
        required=False,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        reg_data = interaction.client.temp_registration_data
        reg_data.avatar_url = self.avatar_url.value.strip() if self.avatar_url.value else None

        # Show summary
        description = (
            "\"Does this look right?\"\n\n"
            "The clerk slips you a shiny new ID with your information."
        )

        embed = discord.Embed(
            title="📋 Registration Summary",
            description=description,
            color=discord.Color.blurple(),
        )

        embed.add_field(name="🏷️ Name", value=reg_data.trainer_name, inline=True)
        embed.add_field(name="💬 Pronouns", value=reg_data.pronouns, inline=True)
        embed.add_field(name="🎂 Age", value=reg_data.age, inline=True)
        embed.add_field(name="🎉 Birthday", value=reg_data.birthday, inline=True)
        embed.add_field(name="🌍 Home Region", value=reg_data.home_region.title(), inline=True)

        if reg_data.bio:
            embed.add_field(name="📝 About You", value=reg_data.bio, inline=False)

        stats_summary = f"Boon: **{get_stat_display_name(reg_data.boon_stat)}** | Bane: **{get_stat_display_name(reg_data.bane_stat)}**"
        embed.add_field(name="📊 Star Traits", value=stats_summary, inline=False)

        if reg_data.avatar_url:
            embed.set_thumbnail(url=reg_data.avatar_url)

        embed.set_footer(text="Choose an option below")

        view = ConfirmationView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class AvatarStepView(View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Add Photo", style=discord.ButtonStyle.primary)
    async def photo_button(self, interaction: discord.Interaction, button: Button):
        modal = AvatarModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        reg_data = interaction.client.temp_registration_data
        reg_data.avatar_url = None

        description = (
            "\"Does this look right?\"\n\n"
            "The clerk slips you a shiny new ID with your information."
        )

        embed = discord.Embed(
            title="📋 Registration Summary",
            description=description,
            color=discord.Color.blurple(),
        )

        embed.add_field(name="🏷️ Name", value=reg_data.trainer_name, inline=True)
        embed.add_field(name="💬 Pronouns", value=reg_data.pronouns, inline=True)
        embed.add_field(name="🎂 Age", value=reg_data.age, inline=True)
        embed.add_field(name="🎉 Birthday", value=reg_data.birthday, inline=True)
        embed.add_field(name="🌍 Home Region", value=reg_data.home_region.title(), inline=True)

        if reg_data.bio:
            embed.add_field(name="📝 About You", value=reg_data.bio, inline=False)

        stats_summary = f"Boon: **{get_stat_display_name(reg_data.boon_stat)}** | Bane: **{get_stat_display_name(reg_data.bane_stat)}**"
        embed.add_field(name="📊 Star Traits", value=stats_summary, inline=False)

        if reg_data.avatar_url:
            embed.set_thumbnail(url=reg_data.avatar_url)

        embed.set_footer(text="Choose an option below")

        view = ConfirmationView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# Step 7: Final Confirmation
class ConfirmationView(View):
    """Confirmation with ability to go back"""

    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="Yes, it's perfect!", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        """Complete registration"""
        await self.complete_registration(interaction)
        self.stop()

    @discord.ui.button(label="No, let's go back", style=discord.ButtonStyle.danger, emoji="❌")
    async def back_button(self, interaction: discord.Interaction, button: Button):
        """Show step selection"""
        embed = discord.Embed(
            title="📝 Edit Registration",
            description="\"Hmm... Okay, which part should be changed?\"",
            color=discord.Color.orange()
        )

        view = EditStepView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        self.stop()

    async def complete_registration(self, interaction: discord.Interaction):
        """Complete registration and create trainer profile"""
        reg_data = interaction.client.temp_registration_data

        success = interaction.client.player_manager.create_player(
            discord_user_id=reg_data.user_id,
            trainer_name=reg_data.trainer_name,
            avatar_url=reg_data.avatar_url,
            boon_stat=reg_data.boon_stat,
            bane_stat=reg_data.bane_stat,
            pronouns=reg_data.pronouns,
            age=reg_data.age,
            birthday=reg_data.birthday,
            home_region=reg_data.home_region,
            bio=reg_data.bio,
        )

        if not success:
            embed = EmbedBuilder.error(
                "Registration Failed",
                "You already have a trainer profile! Use `/menu` to continue your journey.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        description = (
            f"Welcome to Reverie City, **{reg_data.trainer_name}**! ✨\n\n"
            "\"Alright, looks like you're all set! Enjoy your stay, and may all your dreams come true in Reverie!\"\n\n"
            "Use `/phone` to open your Rotom-Phone."
        )

        embed = discord.Embed(
            title="🎉 Registration Complete!",
            description=description,
            color=discord.Color.gold(),
        )

        if reg_data.avatar_url:
            embed.set_thumbnail(url=reg_data.avatar_url)

        await interaction.response.send_message(embed=embed, ephemeral=False)

        # Cleanup
        if hasattr(interaction.client, "temp_registration_data"):
            del interaction.client.temp_registration_data


# Edit Step Selection View
class EditStepView(View):
    """Allow user to select which step to edit"""

    def __init__(self):
        super().__init__(timeout=120)

        options = [
            discord.SelectOption(label="Name", value="name", emoji="🏷️"),
            discord.SelectOption(label="Pronouns", value="pronouns", emoji="💬"),
            discord.SelectOption(label="Age", value="age", emoji="🎂"),
            discord.SelectOption(label="Birthday", value="birthday", emoji="🎉"),
            discord.SelectOption(label="Home Region", value="region", emoji="🌍"),
            discord.SelectOption(label="Bio", value="bio", emoji="📝"),
            discord.SelectOption(label="Star Traits", value="stats", emoji="📊"),
            discord.SelectOption(label="Photo", value="photo", emoji="📸"),
        ]

        select = Select(
            placeholder="Choose what to edit...",
            options=options,
            custom_id="edit_select"
        )
        select.callback = self.edit_callback
        self.add_item(select)

    async def edit_callback(self, interaction: discord.Interaction):
        """Handle edit selection"""
        choice = interaction.data['values'][0]

        if choice == "name":
            modal = NameModal()
            await interaction.response.send_modal(modal)
        elif choice == "pronouns":
            modal = PronounsModal()
            await interaction.response.send_modal(modal)
        elif choice == "age":
            modal = AgeModal()
            await interaction.response.send_modal(modal)
        elif choice == "birthday":
            modal = BirthdayModal()
            await interaction.response.send_modal(modal)
        elif choice == "region":
            embed = discord.Embed(
                title="📝 Registration Center",
                description="\"What's your home region?\"",
                color=discord.Color.blue()
            )
            view = RegionSelectView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        elif choice == "bio":
            view = BioStepView()
            embed = discord.Embed(
                title="📝 Registration Center",
                description="\"Tell me a little bit about yourself!\"",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        elif choice == "stats":
            embed = discord.Embed(
                title="✨ Choose Your Star Traits",
                description=(
                    "Every trainer has 5 Star Traits:\n\n"
                    "**Heart** - Empathy & connection\n"
                    "**Insight** - Perception & intellect\n"
                    "**Charisma** - Charm & influence\n"
                    "**Fortitude** - Strength & willpower\n"
                    "**Clarity** - Focus & discipline\n\n"
                    "Choose one **Boon** (Rank 2) and one **Bane** (Rank 0)."
                ),
                color=discord.Color.blue(),
            )
            view = SocialStatsView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        elif choice == "photo":
            embed = discord.Embed(
                title="📸 Character Photo",
                description=(
                    "\"Would you like to submit a photo for your ID?\"\n\n"
                    "You can provide an image URL, or skip this step."
                ),
                color=discord.Color.blue(),
            )
            view = AvatarStepView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class RegistrationCog(commands.Cog):
    """Handles trainer registration"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="register",
        description="Create your trainer profile and begin your journey",
    )
    async def register(self, interaction: discord.Interaction):
        """Register as a new trainer"""
        await interaction.response.defer(ephemeral=True)

        if self.bot.player_manager.player_exists(interaction.user.id):
            embed = EmbedBuilder.error(
                "Already Registered",
                "You already have a trainer profile! Use `/menu` to continue your journey.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Initialize registration data
        interaction.client.temp_registration_data = RegistrationData(interaction.user.id)

        description = (
            "You've just taken your very first steps into the beautiful city of dreams.\n\n"
            "You step up to the counter at the registration center, and the clerk smiles at you.\n\n"
            "\"Welcome to Reverie City! We're so happy to have you! I'm sure you're looking forward to seeing the sights!\"\n\n"
            "\"Let's get started on registering your ID!\""
        )

        embed = discord.Embed(
            title="🌆 Welcome to Reverie City!",
            description=description,
            color=discord.Color.green(),
        )
        embed.set_footer(text="Press the button below to begin")

        view = WelcomeView()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class WelcomeView(View):
    """Initial welcome view with start button"""

    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Begin Registration", style=discord.ButtonStyle.success, emoji="📝")
    async def begin_button(self, interaction: discord.Interaction, button: Button):
        """Start the registration flow"""
        embed = discord.Embed(
            title="📝 Registration Center",
            description="\"Could you tell me your name, please?\"",
            color=discord.Color.blue()
        )

        modal = NameModal()
        await interaction.response.send_modal(modal)


async def setup(bot):
    """Setup function for loading the cog"""
    await bot.add_cog(RegistrationCog(bot))
