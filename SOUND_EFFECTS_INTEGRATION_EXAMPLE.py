"""
Example: How to integrate sound effects into battle flow

This file demonstrates where and how to call sound effects during battles.
Copy these patterns into your battle cog where appropriate.
"""

import asyncio

# ============================================================
# EXAMPLE 1: Send Out Pokemon (Initial)
# ============================================================

async def example_send_out_pokemon(battle_id, pokemon, music_manager):
    """
    Play sound when initially sending out a Pokemon.
    Sound sequence: throw → switch → pokemon cry
    """

    # Check if this battle has music enabled
    if battle_id in battles_with_music and music_manager.current_session:
        # Get Pokemon's dex number
        dex_number = pokemon.species_dex_number

        # Play send out sound
        print(f"🎵 Playing send out sound for {pokemon.species_name}...")
        duration = await music_manager.play_send_out_sound(dex_number)

        # Wait for sound to finish before showing next embed
        if duration > 0:
            await asyncio.sleep(duration)

    # Now show the battle embed (Pokemon has been sent out)
    # ... (your embed code here)


# ============================================================
# EXAMPLE 2: Switch Pokemon
# ============================================================

async def example_switch_pokemon(battle_id, old_pokemon, new_pokemon, music_manager):
    """
    Play sound when switching Pokemon.
    Sound sequence: switch → pause → throw → switch → pokemon cry
    """

    # Check if this battle has music enabled
    if battle_id in battles_with_music and music_manager.current_session:
        # Get new Pokemon's dex number
        dex_number = new_pokemon.species_dex_number

        # Play switch sound
        print(f"🎵 Playing switch sound for {new_pokemon.species_name}...")
        duration = await music_manager.play_switch_sound(dex_number)

        # Wait for sound to finish
        if duration > 0:
            await asyncio.sleep(duration)

    # Now show the switch embed
    # ... (your embed code here)


# ============================================================
# EXAMPLE 3: Pokemon Faints
# ============================================================

async def example_pokemon_faint(battle_id, fainted_pokemon, music_manager):
    """
    Play sound when a Pokemon faints.
    Sound sequence: sad cry → faint noise
    """

    # Check if this battle has music enabled
    if battle_id in battles_with_music and music_manager.current_session:
        # Get fainted Pokemon's dex number
        dex_number = fainted_pokemon.species_dex_number

        # Play faint sound
        print(f"🎵 Playing faint sound for {fainted_pokemon.species_name}...")
        duration = await music_manager.play_faint_sound(dex_number)

        # Wait for sound to finish
        if duration > 0:
            await asyncio.sleep(duration)

    # Now show the faint embed
    # ... (your embed code here)


# ============================================================
# EXAMPLE 4: Full Battle Flow Integration
# ============================================================

async def example_full_battle_turn(battle, action, music_manager, battles_with_music):
    """
    Example showing a complete battle turn with sound effects.
    """

    battle_id = battle.battle_id
    has_music = battle_id in battles_with_music

    # 1. If action is SWITCH
    if action.action_type == "SWITCH":
        old_pokemon = battle.get_active_pokemon(action.player_id)
        new_pokemon = battle.get_pokemon_by_id(action.target_pokemon_id)

        # Play switch sound and wait
        if has_music and music_manager.current_session:
            dex_number = new_pokemon.species_dex_number
            duration = await music_manager.play_switch_sound(dex_number)
            if duration > 0:
                await asyncio.sleep(duration)

        # Show switch embed
        await interaction.followup.send(embed=switch_embed)

    # 2. If action is ATTACK and causes faint
    elif action.action_type == "ATTACK":
        # ... execute attack logic ...

        # Check if target fainted
        if target_pokemon.current_hp <= 0:
            # Play faint sound and wait
            if has_music and music_manager.current_session:
                dex_number = target_pokemon.species_dex_number
                duration = await music_manager.play_faint_sound(dex_number)
                if duration > 0:
                    await asyncio.sleep(duration)

            # Show faint embed
            await interaction.followup.send(embed=faint_embed)

            # If player needs to send out new Pokemon
            if battle.needs_switch(player_id):
                # ... show switch selection UI ...
                # ... player selects new Pokemon ...

                # Play send out sound for new Pokemon
                if has_music and music_manager.current_session:
                    dex_number = new_pokemon.species_dex_number
                    duration = await music_manager.play_send_out_sound(dex_number)
                    if duration > 0:
                        await asyncio.sleep(duration)

                # Show send out embed
                await interaction.followup.send(embed=send_out_embed)


# ============================================================
# EXAMPLE 5: Battle Start
# ============================================================

async def example_battle_start(battle, trainer, opponent, music_manager, battles_with_music):
    """
    Example showing battle start with sound effects for both trainers.
    """

    battle_id = battle.battle_id
    has_music = battle_id in battles_with_music

    # Show battle intro embed
    await interaction.followup.send(embed=intro_embed)

    # Trainer sends out first Pokemon
    trainer_pokemon = battle.get_active_pokemon(trainer.user_id)
    if has_music and music_manager.current_session:
        duration = await music_manager.play_send_out_sound(trainer_pokemon.species_dex_number)
        if duration > 0:
            await asyncio.sleep(duration)

    await interaction.followup.send(embed=trainer_send_out_embed)

    # Small delay between send outs
    await asyncio.sleep(0.5)

    # Opponent sends out first Pokemon
    opponent_pokemon = battle.get_active_pokemon(opponent.trainer_id)
    if has_music and music_manager.current_session:
        duration = await music_manager.play_send_out_sound(opponent_pokemon.species_dex_number)
        if duration > 0:
            await asyncio.sleep(duration)

    await interaction.followup.send(embed=opponent_send_out_embed)

    # Battle is ready, show action menu
    await interaction.followup.send(embed=battle_menu_embed, view=battle_view)


# ============================================================
# EXAMPLE 6: Battle Cleanup
# ============================================================

async def example_battle_cleanup(battle_id, music_manager, battles_with_music):
    """
    Clean up sound effects when battle ends.
    """

    # Clean up music and sound effects
    if battle_id in battles_with_music:
        await music_manager.cancel_session(battle_id)
        music_manager.cleanup_sound_effects()
        del battles_with_music[battle_id]


# ============================================================
# KEY POINTS
# ============================================================

"""
1. Always check if battle has music enabled:
   if battle_id in battles_with_music and music_manager.current_session:

2. Get Pokemon's dex number:
   dex_number = pokemon.species_dex_number

3. Play appropriate sound and get duration:
   duration = await music_manager.play_send_out_sound(dex_number)
   duration = await music_manager.play_switch_sound(dex_number)
   duration = await music_manager.play_faint_sound(dex_number)

4. Wait for sound to finish before showing next embed:
   if duration > 0:
       await asyncio.sleep(duration)

5. Clean up when battle ends:
   music_manager.cleanup_sound_effects()

6. Sounds automatically pause music and resume it after playing.

7. If cries folder doesn't exist, methods return 0.0 immediately.
"""
