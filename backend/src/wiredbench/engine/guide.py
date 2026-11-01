"""Plain explanations of the boxes the engine simulates. Names and other boxes come from the catalogue.

Examples are ideas for using a box. How far its behaviour can be trusted is the box's status, not this text.
"""

from __future__ import annotations

GUIDE: dict[str, tuple[str, str]] = {
    "wf_trg_walks_on_furni": (
        "Runs when a user steps onto a picked furni.",
        "Open a gate when someone stands on a tile.",
    ),
    "wf_trg_walks_off_furni": (
        "Runs when a user steps off a picked furni.",
        "Stop a timer when someone leaves a seat.",
    ),
    "wf_trg_click_furni": (
        "Runs when a user clicks a picked furni.",
        "Make a sign show a message when clicked.",
    ),
    "wf_trg_state_changed": (
        "Runs when a user changes the state of a picked furni.",
        "Flip a lamp when someone uses a switch.",
    ),
    "wf_trg_stuff_state": (
        "Runs when a picked furni's state changes, whatever changed it.",
        "React to a switch that another stack flipped.",
    ),
    "wf_trg_says_something": (
        "Runs when a user says a keyword.",
        "Give a point when someone says a code word.",
    ),
    "wf_trg_enter_room": ("Runs when a user enters the room.", "Greet each visitor."),
    "wf_trg_leave_room": ("Runs when a user leaves the room.", "Clear a user's game variables."),
    "wf_trg_room_initializes": ("Runs when the room starts.", "Set a room counter to its starting value."),
    "wf_trg_periodically": ("Runs again and again after a set time.", "Update a score every 10 seconds."),
    "wf_trg_period_short": ("Runs again and again at a short interval.", "Check a fast game's state."),
    "wf_trg_period_long": ("Runs again and again at a long interval.", "Save progress every few minutes."),
    "wf_trg_at_given_time": (
        "Runs once when the room timer reaches a set time.",
        "End a round after 60 seconds.",
    ),
    "wf_trg_recv_signal": (
        "Runs when a picked antenna receives a signal.",
        "Let one stack start another, keeping its user.",
    ),
    "wf_trg_var_changed": (
        "Runs when a chosen variable changes.",
        "Open a door when a score reaches a target.",
    ),
    "wf_cnd_has_var": ("Passes if the user has a chosen variable.", "Only let on-duty staff use a door."),
    "wf_cnd_neg_has_var": (
        "Passes if the user does not have a chosen variable.",
        "Give a starter reward only once.",
    ),
    "wf_cnd_var_age_match": (
        "Compares how long ago a variable was given or last changed.",
        "Only pass once a player has held a role for an hour.",
    ),
    "wf_cnd_var_val_match": ("Compares a variable with a value.", "Only pass when a score is at least 10."),
    "wf_cnd_trggrer_on_frn": (
        "Passes if the user is on a picked furni.",
        "Check someone is still in their seat.",
    ),
    "wf_cnd_not_trggrer_on": (
        "Passes if the user is not on a picked furni.",
        "Stop a timer once someone has left.",
    ),
    "wf_cnd_furnis_hv_avtrs": ("Passes if users are on all picked furni.", "Start when every seat is taken."),
    "wf_cnd_not_hv_avtrs": (
        "Passes if picked furni have no users on them.",
        "Only close a gate when nobody is in it.",
    ),
    "wf_cnd_has_furni_on": (
        "Passes if picked furni have other furni on them.",
        "Check a block sits on a pressure plate.",
    ),
    "wf_cnd_not_furni_on": ("Passes if picked furni have no furni on them.", "Check a tile is clear."),
    "wf_cnd_stuff_is": ("Passes if picked furni match their saved state.", "Only pass when a lever is on."),
    "wf_cnd_not_stuff_is": (
        "Passes if picked furni do not match their saved state.",
        "Only pass when a lever is off.",
    ),
    "wf_cnd_user_count_in": (
        "Passes if the number of users is within a range.",
        "Start a game with at least two players.",
    ),
    "wf_cnd_not_user_count": (
        "Passes if the number of users is outside a range.",
        "Warn when the room is empty or too full.",
    ),
    "wf_cnd_triggerer_match": (
        "Passes if the user has a chosen name.",
        "Let only the owner use a control panel.",
    ),
    "wf_cnd_not_triggerer_match": (
        "Passes if the user does not have a chosen name.",
        "Keep the owner out of a player count.",
    ),
    "wf_cnd_time_less_than": (
        "Passes if the room timer is below a time.",
        "Accept answers only in the first minute.",
    ),
    "wf_cnd_time_more_than": ("Passes if the room timer is past a time.", "Open an exit after a delay."),
    "wf_slc_furni_area": ("Selects furni inside a rectangle of the room.", "Reset every tile in one zone."),
    "wf_slc_users_area": ("Selects users inside a rectangle of the room.", "Message everyone in the lobby."),
    "wf_slc_furni_altitude": (
        "Selects furni by how high they stand.",
        "Find everything stacked above a floor.",
    ),
    "wf_slc_furni_onfurni": (
        "Selects furni by how they stack with picked furni.",
        "Move what sits on a table.",
    ),
    "wf_slc_furni_picks": ("Selects picked furni for the stack's effects.", "Target several lamps at once."),
    "wf_slc_furni_bytype": (
        "Selects furni of the same types as those picked.",
        "Target every chair of one kind.",
    ),
    "wf_slc_furni_signal": ("Selects the furni carried by a signal.", "Act on the furni another stack sent."),
    "wf_slc_furni_with_var": (
        "Selects furni holding a chosen variable.",
        "Find every tile marked as active.",
    ),
    "wf_slc_users_signal": ("Selects the users carried by a signal.", "Act on the user another stack sent."),
    "wf_slc_users_with_var": ("Selects users holding a chosen variable.", "Update everyone who is on duty."),
    "wf_slc_users_onfurni": ("Selects users on picked furni.", "Teleport everyone standing on a pad."),
    "wf_slc_users_byname": ("Selects users by name.", "Message a chosen group of people."),
    "wf_xtra_exec_in_order": (
        "Runs the stack's effects in order rather than a random one.",
        "Set a value, then read it.",
    ),
    "wf_xtra_random": ("Runs some of the stack's effects, chosen at random.", "Pick a random prize."),
    "wf_xtra_unseen": (
        "Runs one effect at a time, using each before repeating.",
        "Cycle through messages evenly.",
    ),
    "wf_xtra_or_eval": (
        "Changes how many of the conditions must pass.",
        "Pass if any one of two checks is true.",
    ),
    "wf_xtra_execution_limit": ("Limits how often a stack can run.", "Stop a button being spammed."),
    "wf_xtra_filter_users": ("Limits how many selected users are used.", "Pick one winner from a crowd."),
    "wf_xtra_filter_furni": ("Limits how many selected furni are used.", "Light only three tiles of many."),
    "wf_xtra_filter_users_by_var": (
        "Keeps the users with the highest or lowest variable.",
        "Find the top scorer.",
    ),
    "wf_xtra_text_output_username": (
        "Adds a placeholder for the user's name to a message.",
        "Say hello using $(user).",
    ),
    "wf_xtra_text_output_variable": (
        "Adds a placeholder for a variable's value to a message.",
        "Show a score using $(score).",
    ),
    "wf_xtra_var_text_connector": ("Turns a variable's numbers into words.", "Show 3 as carrot."),
    "wf_xtra_var_time_util": ("Marks a variable as holding time values.", "Count seconds spent on duty."),
    "wf_var_user": ("Defines a variable that users can hold.", "Keep a score for each player."),
    "wf_var_furni": ("Defines a variable that furni can hold.", "Mark which tile holds which note."),
    "wf_var_room": ("Defines one variable for the whole room.", "Keep a round number."),
    "wf_var_context": (
        "Defines a variable that lasts only while a stack runs.",
        "Hold a value between two effects.",
    ),
    "wf_act_give_var": ("Gives a user or furni a variable.", "Mark a player as joined."),
    "wf_act_remove_var": (
        "Removes a variable from a user or furni.",
        "Clear a player's status when they leave.",
    ),
    "wf_act_change_var_val": ("Sets or calculates a variable's value.", "Add 1 to a score."),
    "wf_act_send_signal": ("Sends a signal to picked antennas.", "Start a shared stack from several places."),
    "wf_act_neg_send_signal": (
        "Sends a signal when the stack's conditions fail.",
        "Report a failed check to another stack.",
    ),
    "wf_act_call_stacks": (
        "Runs other stacks, skipping their triggers and conditions.",
        "Reuse one set of effects.",
    ),
    "wf_act_neg_call_stacks": ("Runs other stacks when the stack's conditions fail.", "Run a fallback."),
    "wf_act_toggle_state": ("Moves picked furni to their next state.", "Flip a lamp."),
    "wf_act_toggle_to_rnd": ("Sets picked furni to a random state.", "Roll a dice."),
    "wf_act_show_message": ("Shows a private message to a user.", "Tell a player their score."),
    "wf_act_log": ("Writes a line to the WIRED log.", "Follow what a stack is doing."),
    "wf_act_neg_log": ("Writes a log line when the stack's conditions fail.", "See why a check failed."),
    "wf_act_reset_timers": ("Resets the room's timers.", "Start a new round."),
    "wf_act_teleport_to": ("Teleports a user to a picked furni.", "Send a player back to the start."),
    "wf_act_user_to_furni": ("Moves a user to a picked furni.", "Walk a player to a seat."),
    "wf_act_move_rotate": ("Moves or turns picked furni.", "Slide a door open."),
    "wf_act_control_clock": ("Starts, stops, pauses or resets a counter.", "Start a round's clock."),
    "wf_act_adjust_clock": ("Changes the time on a counter.", "Add ten seconds for a bonus."),
    "wf_cnd_counter_time_matches": ("Compares a counter's time.", "Only open a door in the first minute."),
    "wf_cnd_team_has_score": ("Compares a team's score.", "Open the prize room at 50 points."),
    "wf_trg_clock_counter": ("Runs when a counter counts up to a time.", "End the round at two minutes."),
    "wf_act_set_highlight": ("Outlines, tints or darkens furni or users.", "Show which tile is safe."),
    "wf_act_set_visibility": ("Makes furni or users invisible or visible.", "Hide a secret door."),
    "wf_xtra_varfx_number": ("Shows a variable as a number over its holders.", "Show each player's coins."),
    "wf_xtra_varfx_levelling": (
        "Shows a variable as level progress over its holders.",
        "Show a player's rank.",
    ),
    "wf_xtra_varfx_prog": (
        "Shows a variable as a progress bar over its holders.",
        "Show how full a tank is.",
    ),
    "wf_xtra_varfx_status": ("Shows a variable as a status bar over its holders.", "Show a player's energy."),
    "wf_xtra_varfx_hp": ("Shows a variable as health over its holders.", "Show health in a battle."),
    "wf_xtra_varfx_boss": ("Shows a variable as a wide boss bar over its holders.", "Show a boss's health."),
    "wf_xtra_mov_carry_users": (
        "Moves users along with the furni they stand on.",
        "Build a moving platform.",
    ),
    "wf_act_join_team": ("Puts users in a team.", "Sort players into red and blue."),
    "wf_act_leave_team": ("Takes users out of their team.", "Clear teams when a round ends."),
    "wf_act_give_score": (
        "Gives points to a user's team during a game.",
        "Score when a player reaches a goal.",
    ),
    "wf_act_give_score_tm": (
        "Gives points to a chosen team during a game.",
        "Reward red for holding a zone.",
    ),
    "wf_cnd_actor_in_team": ("Passes if the user is in a team.", "Only let red through a gate."),
    "wf_cnd_not_in_team": ("Passes if the user is not in a team.", "Keep players without a team out."),
    "wf_slc_users_team": ("Selects the users in a team.", "Message everyone on blue."),
    "wf_trg_game_starts": ("Runs when a game starts.", "Open the arena doors."),
    "wf_trg_game_ends": ("Runs when a game ends.", "Send everyone back to the lobby."),
    "wf_act_rel_mov": ("Moves picked furni by a set number of tiles.", "Shift a platform three tiles along."),
    "wf_act_set_altitude": ("Raises, lowers or sets the height of furni.", "Lift a bridge into place."),
    "wf_act_furni_to_user": (
        "Moves furni onto a user's tile.",
        "Make a marker follow the player who clicked.",
    ),
    "wf_act_furni_to_furni": ("Moves furni onto the tile of another furni.", "Return a ball to its spot."),
    "wf_act_move_rotate_user": ("Moves users one tile or turns them.", "Push a player off a trap."),
}
