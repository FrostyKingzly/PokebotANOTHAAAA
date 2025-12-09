# Allowed Starter Pokemon Configuration
# 
# This file controls which Pokemon can be selected as starters.
# You can customize this list however you want!
#
# Options:
# 1. List specific dex numbers: ALLOWED_STARTERS = [1, 4, 7, 25, 152, ...]
# 2. Use "first_forms_only" to only allow base evolution forms
# 3. Use "all_non_legendary" to allow all non-legendary Pokemon
#
# Current setting uses a curated list of popular first-form Pokemon

# Choose your starter selection mode:
STARTER_MODE = "all_species"  # Options: "curated_list", "first_forms_only", "all_non_legendary", "all_species"

# Curated list of allowed starter Pokemon (by dex number)
# This is a handpicked selection of popular and iconic first-form Pokemon
ALLOWED_STARTERS = [
    # Kanto Starters & Evolutions
    1, 4, 7,  # Bulbasaur, Charmander, Squirtle
    
    # Other Popular Kanto
    25,  # Pikachu
    133, # Eevee
    104, # Cubone
    27,  # Sandshrew
    37,  # Vulpix
    52,  # Meowth
    58,  # Growlithe
    63,  # Abra
    66,  # Machop
    74,  # Geodude
    92,  # Gastly
    129, # Magikarp
    147, # Dratini
    
    # Johto Starters
    152, 155, 158,  # Chikorita, Cyndaquil, Totodile
    
    # Other Johto
    172, # Pichu
    173, # Cleffa
    174, # Igglybuff
    175, # Togepi
    179, # Mareep
    
    # Hoenn Starters
    252, 255, 258,  # Treecko, Torchic, Mudkip
    
    # Other Hoenn
    261, # Poochyena
    263, # Zigzagoon
    276, # Taillow
    280, # Ralts
    287, # Slakoth
    304, # Aron
    316, # Gulpin
    371, # Bagon
    
    # Sinnoh Starters
    387, 390, 393,  # Turtwig, Chimchar, Piplup
    
    # Other Sinnoh
    403, # Shinx
    418, # Buizel
    
    # Unova Starters
    495, 498, 501,  # Snivy, Tepig, Oshawott
    
    # Other Unova
    504, # Patrat
    506, # Lillipup
    509, # Purrloin
    519, # Pidove
    
    # Kalos Starters
    650, 653, 656,  # Chespin, Fennekin, Froakie
    
    # Other Kalos
    659, # Bunnelby
    661, # Fletchling
    
    # Alola Starters
    722, 725, 728,  # Rowlet, Litten, Popplio
    
    # Other Alola
    734, # Yungoos
    
    # Galar Starters
    810, 813, 816,  # Grookey, Scorbunny, Sobble
    
    # Other Galar
    819, # Skwovet
    821, # Rookidee
    
    # Paldea Starters
    906, 909, 912,  # Sprigatito, Fuecoco, Quaxly
]

# If you want to allow ONLY first evolution forms (no middle or final evolutions)
# Set STARTER_MODE = "first_forms_only" above
# This will automatically filter to only show base forms

# If you want to allow ALL non-legendary Pokemon
# Set STARTER_MODE = "all_non_legendary" above
# This will show all Pokemon except legendaries/mythicals/ultra beasts

# Evolution chains for first-form filtering
# Maps Pokemon ID to whether it's a first form (True) or evolved form (False)
# This is auto-generated but you can override specific Pokemon here
FIRST_FORM_OVERRIDES = {
    # Example: If you want to allow a middle evolution as a starter
    # 17: True,  # Pidgeotto (normally would be excluded)
}

# Custom filters
# Add dex numbers here to EXCLUDE specific Pokemon even if they'd normally be allowed
EXCLUDED_POKEMON = [
    # Example: 133,  # Eevee (if you don't want Eevee as a starter)
]

# Pagination settings
STARTERS_PER_PAGE = 25  # Discord dropdown limit, don't change this
