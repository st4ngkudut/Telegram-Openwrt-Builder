# handlers/constants.py

# --- STATE CONVERSATIONHANDLER ---

(
    # --- Settings States ---
    SELECT_MODE,                # 0
    # Official
    MENU,                       # 1
    SELECT_BUILD_SOURCE,        # 2
    SELECT_VERSION_MAJOR,       # 3
    SELECT_VERSION_MINOR,       # 4
    SELECT_TARGET,              # 5
    SELECT_SUBTARGET,           # 6
    SELECT_PROFILE,             # 7
    AWAITING_PACKAGES,          # 8
    AWAITING_ROOTFS_SIZE,       # 9
    AWAITING_LEECH_DEST_OFFICIAL, # 10
    # Customization
    CUSTOM_MENU,                # 11
    AWAITING_CUSTOM_REPOS,      # 12
    AWAITING_UCI_SCRIPT,        # 13
    # Amlogic
    AML_MENU,                   # 14
    AWAITING_AML_ROOTFS_URL,    # 15
    AWAITING_AML_BOARD,         # 16
    AWAITING_AML_ROOTFS_SIZE,   # 17
    AWAITING_LEECH_DEST_AML,    # 18
    AWAITING_AML_KERNEL_TAG,    # 19
    AWAITING_AML_BUILDER_NAME,  # 20
    AWAITING_AML_KERNEL,        # 21

    # --- Build States ---
    SELECT_BUILD_MODE,          # 22
    CONFIRM_BUILD,              # 23
    AWAITING_PROFILE_FIX,       # 24

    # --- Upload States ---
    UPLOAD_ROOTFS,              # 25
    UPLOAD_IPK,                 # 26
    
    # --- Cleanup States ---
    CLEANUP_ALL_CONFIRM_1,      # 27
    AWAITING_DELETION_PHRASE,   # 28

    # --- Future States ---
    CHAIN_CONFIRM_AML,          # 29
    PREFLIGHT_CHECK_AML,        # 30
) = range(31)
