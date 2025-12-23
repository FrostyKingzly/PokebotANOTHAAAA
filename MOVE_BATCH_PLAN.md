# Move Implementation Batching Plan

This plan sequences the remaining move-behavior work into focused batches. Each batch groups moves by mechanic so we can add logic and tests incrementally without mixing unrelated effects.

## Batch 1 (start here): Core battle-flow behaviors
Moves whose primary effects change turn flow (two-turn attacks), field control (force-switch, partial trapping), guaranteed status, self-switching, or weather. Fixes here unblock many battle scripts and are heavily represented in the audit report.

**Two-turn / charging moves**
- Razor Wind
- Fly
- Solar Beam
- Dig
- Skull Bash
- Sky Attack
- Bounce
- Shadow Force
- Sky Drop
- Freeze Shock
- Ice Burn
- Phantom Force
- Geomancy

**Force-switch effects**
- Whirlwind
- Roar
- Circle Throw
- Dragon Tail

**Self-switching moves**
- Teleport
- Baton Pass
- U-turn
- Volt Switch
- Parting Shot
- Flip Turn
- Shed Tail
- Chilly Reception

**Partial trapping / binding**
- Bind
- Wrap
- Fire Spin
- Clamp
- Whirlpool
- Sand Tomb
- Magma Storm
- Infestation
- Snap Trap
- Thunder Cage

**Guaranteed status (confusion/sleep)**
- Supersonic
- Confuse Ray
- Sweet Kiss
- Swagger
- Flatter
- Dark Void

**Weather setters**
- Sandstorm
- Rain Dance
- Sunny Day
- Snowscape

**Healing moves**
- Rest
- Morning Sun
- Synthesis
- Moonlight
- Shore Up

**One-hit KO flagging**
- Guillotine
- Horn Drill
- Fissure
- Sheer Cold

## Batch 2: Variable/fixed damage moves
Moves with power that depends on HP, weight, friendship, stage boosts, or set values (e.g., Counter, Seismic Toss, Low Kick, Electro Ball, Beat Up, Reversal/Flail line, Natural Gift, Fling, Z-Move base powers, etc.).

## Batch 3: Multi-hit and duration-based mechanics
Special-hit-count logic (e.g., Present, Population Bomb, multi-hit odds), damage scaling over consecutive turns, or capped duration effects (e.g., Fury Attack family, Triple Axel), plus partial-trap damage tuning.

## Batch 4: Field/terrain/room effects
Weather/terrain adjacencies, Trick Room/Gravity-style effects, and pledge combos that create field hazards (Rainbow/Sea of Fire/Swamp) with their per-turn handling.

## Batch 5: Signature and special-case moves
Unique mechanics not covered above (e.g., Shed Tail substitute handoff, Court Change, moves that copy/steal effects, Doom Desire/Future Sight timing nuances, etc.), plus validation against the remaining audit warnings.

## Batch 6: Regression sweep and audit closure
Re-run the move audit, fill any remaining gaps, and add integration tests covering representative examples from each mechanic group to prevent regressions.
