# ai/action_fixer/_constants.py - shared constants split from action_fixer.py
# action_fixer.py - Post-processing logic để fix AI action names và merge steps


# ============================================================================
# SHARED CONSTANTS
# ============================================================================

# Deployment checkbox keywords - used for merging and filtering
DEPLOYMENT_KEYWORDS = [
    # Left column
    "localization",
    "excel",
    "currency",
    "consumables",
    "consumable",
    "faction feud",
    "grab bag",
    "grabbag",
    "chat channels",
    "chat channel",
    "pve",
    "faction mission",
    "merch store",
    "feature setting",
    "invasion",
    "mizz missions",
    "mizz mission",
    "subscription 1.5",
    "feature gate setting",
    "versus shop",
    "league config",
    "champion rewards",
    "battle shop",
    "notification",
    "reactivation flow",
    "auto play",
    "news modal",
    "stat change",
    # Right column
    "gacha events",
    "gacha event",
    "gacha",
    "offers",
    "offer",
    "missions",
    "mission",
    "fight card",
    "fight card v3",
    "cash contract",
    "liveops message",
    "live ops message",
    "rbe",
    "affiliation war contribution",
    "faction lockbox",
    "promo code",
    "subscription & vip",
    "subscription vip",
    "perks",
    "perk",
    "effect cap setting",
    "social box gacha",
    "monthly bonus",
    "versus tournament",
    "tournament",
    "versus",
    "player league",
    "strap and medal",
    "superstars",
    "superstar",
    "boost",
    "faction boss",
    "moment poster",
    "time challenge",
    "social friends",
    "social friend",
    "token",
    # Additional navigation contexts
    "data configs",
    "data config",
    "live events",
    "live event",
    "hyper blueprint",
    "prize wall",
    "shop",
    "store",
    "event",
    "config",
    "blueprint",
    # Toggle All (special)
    "toggle all",
    "toogle all",
    "select all",
    "check all",
]


# ============================================================================
# NAVIGATION PATH MAP - Auto-resolve partial/shorthand paths to full menu paths
# ============================================================================

# Map: destination keyword (lowercase) → full navigation path
# When user says "Vào Faction Feud Event", AI may generate navigate(["Faction Feud Event"])
# This map resolves it to the full path ["Live Events", "Faction Feud", "Faction Feud Event"]


# ============================================================================
# PAGE TAB NAMES - Elements that are in-page tabs/buttons, NEVER sidebar nav items
# ============================================================================
# If the AI generates navigate(["X"]) where X is in this set, it is wrong.
# These elements only exist as tabs/buttons WITHIN a page (e.g. RBE form tabs),
# and must be interacted with via `click`, not `navigate`.
# Bug: AI confuses "Bấm vào tab Contest Superstars" → navigate(["Contest Superstars"])
# which causes navigator to deep-scan sidebar, fail, and crash/refresh the page.
PAGE_TAB_NAMES = {
    "contest superstars",
    "define schedules",
    "add event",
    "add schedule",
    "add css",
    "pvp",
}


NAVIGATION_PATH_MAP = {
    # === Live Events ===
    # Faction Feud
    "faction feud event": ["Live Events", "Faction Feud", "Faction Feud Event"],
    "faction feud": ["Live Events", "Faction Feud"],
    # Gacha
    "gacha event": ["Live Events", "Gacha Event", "Gacha Event"],
    # Offer
    "offer": ["Live Events", "Offer", "Offer"],
    "offer section": ["Live Events", "Offer", "Offer Section"],
    "offer popup manager": ["Live Events", "Offer", "Offer Popup Manager"],
    "shop tier": ["Live Events", "Offer", "Shop Tier"],
    "store preview": ["Live Events", "Offer", "Store Preview"],
    "drip offer": ["Live Events", "Offer", "Drip Offer"],
    # Versus
    "tournament": ["Live Events", "Versus", "Tournament"],
    "versus tournament": ["Live Events", "Versus", "Tournament"],
    "notoriety reset brackets": ["Live Events", "Versus", "Notoriety Reset Brackets"],
    # Mission
    "mission": ["Live Events", "Mission", "Mission"],
    # Fight Card
    "fight card": ["Live Events", "Fight Card", "Fight Card"],
    "fight card v3": ["Live Events", "Fight Card", "Fight Card V3"],
    "fight card slot": ["Live Events", "Fight Card", "Fight Card Slot"],
    # Cash Contract
    "cash contract": ["Live Events", "Cash Contract", "Cash Contract"],
    # RBE
    "rbe": ["Live Events", "RBE", "RBE"],
    "affiliation war contribution": ["Live Events", "RBE", "Affiliation War Contribution"],
    "rules based event": ["Live Events", "RBE"],
    "rules based tournament": ["Live Events", "RBE"],
    # Faction Lockbox
    "faction lockbox": ["Live Events", "Faction Lockbox", "Faction Lockbox"],
    # Faction Boss
    "faction boss event": ["Live Events", "Faction Boss Battle"],
    "faction boss": ["Live Events", "Faction Boss Battle"],
    # Grab Bag
    "grab bag": ["Data Configs", "Grab Bag V2"],
    "grabbag": ["Data Configs", "Grab Bag V2"],
    # LiveOps Message
    "liveops message": ["Live Events", "LiveOps Message", "LiveOps Message"],
    "live ops message": ["Live Events", "LiveOps Message", "LiveOps Message"],
    # Promo Code
    "promo code": ["Live Events", "Promo Code", "Promo Code"],
    # Social Box Gacha
    "social box gacha": ["Live Events", "Social Box Gacha", "Social Box Gacha"],
    # Monthly Bonus
    "monthly bonus": ["Live Events", "Monthly Bonus", "Monthly Bonus"],
    # Prize Wall
    "prize wall": ["Live Events", "Prize Wall", "Prize Wall"],
    # Invasion
    "invasion": ["Live Events", "Invasion", "Invasion"],
    # Time Challenge
    "time challenge": ["Live Events", "Time Challenge", "Time Challenge"],
    # Moment Poster
    "moment poster": ["Live Events", "Moment Poster", "Moment Poster"],
    # PVE
    "pve": ["Live Events", "PVE", "Classic PVE"],
    "chapter": ["Live Events", "PVE", "Chapter"],
    "book": ["Live Events", "PVE", "Book"],
    "book pool": ["Live Events", "PVE", "Book Pool"],
    # Hyper Blueprint
    "hyper blueprint": ["Live Events", "Hyper Blueprint", "Hyper Blueprint"],
    # === Data Configs ===
    "perk": ["Data Configs", "Perk", "Perk"],
    "boost": ["Data Configs", "Boost", "Boost"],
    "superstar": ["Data Configs", "Superstar", "Superstar"],
    "superstars": ["Data Configs", "Superstar", "Superstar"],
    "currency": ["Data Configs", "Inventory", "Currency"],
    "token group configuration": [
        "Data Configs",
        "Inventory",
        "Token Group Configuration",
    ],
    "consumables": ["Data Configs", "Inventory", "Consumables Object"],
    "token": ["Data Configs", "Inventory", "Token"],
    "strap and medal": ["Data Configs", "Strap and Medal", "Strap and Medal"],
    "stat change": ["Data Configs", "Stat Change", "Stat Change"],
    "feature setting": ["Settings", "Feature Setting"],
    "feature gate setting": ["Settings", "Feature Gate Setting"],
    "league config": ["Live Events", "League", "League Config"],
    "champion rewards": ["Data Configs", "Champion Rewards", "Champion Rewards"],
    "player league": ["Live Events", "League", "Player League"],
    "notification": ["Data Configs", "Notification", "Notification"],
    "chat channels": ["Data Configs", "Chat Channels", "Chat Channels"],
    "effect cap setting": ["Data Configs", "Effect Cap Setting", "Effect Cap Setting"],
    "merch store": ["Data Configs", "Merch Store", "Merch Store"],
    "versus shop": ["Data Configs", "Versus Shop", "Versus Shop"],
    "battle shop": ["Data Configs", "Battle Shop", "Battle Shop"],
    "rarity release gate": ["Settings", "Rarity Release Gate"],
    "playgami reward config": ["Settings", "Playgami Reward Config"],
    "localization": ["Data Configs", "Localizations", "Localizations"],
}


# ============================================================================
# POST-PROCESSING: FIX INVALID ACTION NAMES (Deterministic - 100% reliable)
# ============================================================================

# Mapping: invalid action name → valid action name
ACTION_NAME_MAP = {
    # Checkbox / Select variations
    "select_random_ids": "checkbox",
    "select_ids": "checkbox",
    "select_random": "checkbox",
    "check_checkbox": "checkbox",
    "select_checkbox": "checkbox",
    "tick_checkbox": "checkbox",
    "select_rows": "checkbox",
    "choose_ids": "checkbox",
    "pick_random": "checkbox",
    # Download / Export variations
    "export_csv": "download",
    "export": "download",
    "export_file": "download",
    "download_csv": "download",
    "download_file": "download",
    # Upload / Import variations
    "import_csv": "upload",
    "import": "upload",
    "import_file": "upload",
    "upload_csv": "upload",
    "upload_file": "upload",
    # Process / Deploy variations
    "click_logo": "process_deployment",
    "click_logo_the_brick": "process_deployment",
    "click_the_brick": "process_deployment",
    "click_brick": "process_deployment",
    "go_home": "process_deployment",
    "process": "process_deployment",
    "deploy": "process_deployment",
    # Uncheck variations
    "uncheck": "checkbox",
    "uncheck_checkbox": "checkbox",
    "unselect": "checkbox",
    "deselect": "checkbox",
    "untick": "checkbox",
    "uncheck_box": "checkbox",
    # Click button variations
    "click_button": "click",
    "press_button": "click",
    "tap_button": "click",
    # Navigate variations
    "go_to": "navigate",
    "open_page": "navigate",
    "open_menu": "navigate",
    # Edit variations
    "edit": "edit_row",
    "edit_item": "edit_row",
    # Clone variations
    "clone": "clone_row",
    "clone_item": "clone_row",
    "duplicate": "clone_row",
    # Save variations
    "save": "save_form",
    # Reorder / drag-and-drop variations
    "drag": "reorder",
    "drag_drop": "reorder",
    "drag_and_drop": "reorder",
    "move_to": "reorder",
    "move_item": "reorder",
    "move_row": "reorder",
    "drag_to": "reorder",
    "set_priority": "reorder",
    "change_order": "reorder",
    "reorder_item": "reorder",
    # Smart test variations
    "test_cycle": "smart_test_cycle",
    "smart_test": "smart_test_cycle",
    "fuzz_test": "smart_test_cycle",
    # Check fields variations
    "check_field": "check_fields",
    "verify_fields": "check_fields",
    "verify_field": "check_fields",
    "inspect_fields": "check_fields",
    "check_tab_fields": "check_fields",
    "check_tabs": "check_fields",
    "kiem_tra_fields": "check_fields",
}

VALID_ACTIONS = {
    "navigate",
    "checkbox",
    "download",
    "upload",
    "manipulate_csv",
    "smart_test_cycle",
    "clone_row",
    "edit_row",
    "update_form",
    "save_form",
    "scan_tabs",
    "check_fields",
    "click",
    "select",
    "wait",
    "wait_for_page_load",
    "process_deployment",
    "reorder",
}

# Valid deployment options (checkboxes on The Brick home screen).
# Anything outside this set that the AI puts in process_deployment.options is stripped.
_VALID_DEPLOY_OPTIONS = {
    "Localization", "Excel", "Currency", "Consumables", "Faction Feud", "Grab Bag",
    "Chat Channels", "PVE", "Faction Mission", "Merch Store", "Feature Setting",
    "Invasion", "Mizz Missions", "Subscription 1.5", "Feature Gate Setting",
    "Versus Shop", "League Config", "Champion Rewards", "Battle Shop", "Notification",
    "Reactivation Flow & Contest", "Auto Play & Speed Up", "News Modal", "Stat Change",
    "Gacha Events", "Offers", "Missions", "Fight Card", "Fight Card V3", "Cash Contract",
    "LiveOps Message", "RBE", "Faction Lockbox", "Promo Code", "Subscription & VIP",
    "Perks", "Effect Cap Setting", "Social Box Gacha", "Monthly Bonus",
    "Versus Tournament", "Player League", "Strap and Medal", "Superstars", "Boost",
    "Faction Boss", "Moment Poster", "Time Challenge", "Social Friends", "Token",
    "Prize Wall", "Hyper Blueprint", "Live Events", "Data Configs",
}


