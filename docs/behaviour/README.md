# Behaviour comparison: Python engine against Turbo

Written by `scripts/behaviour.py report`; do not edit by hand. Every room the old Python engine's tests
build (`backend/tests/test_engine.py`, `test_guide.py`) with a WIRED box is replayed in both engines,
and what a player could see is compared just before each input and at the end: where users and bots
stand, each furni's tile, turn and state, user-made variables on each holder, and Show Message
whispers. Neither engine has been changed to agree: this lists where they disagree.

Turbo stands the room on a flat floor, saves each box as the client would (the G-Presets export of
the room), moves users straight onto a tile as the Python engine does (not when frozen), stands bots
and hand items, writes API values through the room's Web API, and runs wired every 50 ms and the
avatar cycle every 500 ms, on a clock where the Python engine's time 0 is the same instant.
Some differences are the replay's, not Turbo's; the notes on a scenario say which:
inputs Turbo does not replay (game, detail and toner inputs), user details other than a hand item,
random draws, settings the client's params cannot carry, and floor heights.

Turbo is the reference where it has Habbo's own list: every built-in variable (`@position.x`,
`@position.y`, `@rotation`, `@state` and the rest) and the placeholders boxes print. A difference
only in those is marked *differs, Turbo is the reference*: the Python engine is the one that is
off, and it is not counted as unexplained.

A difference whose cause has been traced is marked *differs, known cause*, with the cause: which
engine is off, or that it is open until a Habbo capture settles it.

## Summary

| Result | Scenarios |
|---|---|
| differs | 2 |
| differs, Turbo is the reference | 10 |
| differs, known cause | 10 |
| same | 249 |
| **total** | **271** |

Scenarios that differ (Turbo's reference ones and known causes left out), by what differs:

| What | Scenarios |
|---|---|
| users | 2 |
| variables | 1 |

0 of the differing scenarios have no note: nothing in the replay explains them.

70 of the 249 matching scenarios show something happening in Python (a
message, a variable, a user or furni changing); the rest are rooms where neither engine changes
anything visible, which match trivially.

## Settings Turbo refused

Boxes whose saved settings (the G-Presets export) Turbo's room would not take; the box then runs as
it stood. Often the export's reading of a field, not Turbo.

| Box | Refusals |
|---|---|
| `wf_act_control_clock` | 8 |
| `wf_act_send_message` | 3 |
| `wf_trg_receive_message` | 3 |
| `wf_act_give_var` | 2 |
| `wf_act_send_signal` | 2 |
| `wf_trg_clock_counter` | 2 |
| `wf_trg_recv_signal` | 1 |
| `wf_act_give_reward` | 1 |
| `wf_act_adjust_clock` | 1 |
| `wf_act_set_highlight` | 1 |
| `wf_trg_click_tile` | 1 |
| `wf_act_place_furni` | 1 |
| `wf_xtra_text_output_variable` | 1 |

## Boxes in unexplained differences

None: every differing scenario has a note.

## Scenarios

### `backend/tests/test_engine.py::test_teleport_and_move#0` (differs)

Notes: random draws.

Boxes: `wf_act_move_rotate`, `wf_act_teleport_to`, `wf_trg_says_something`

First difference at checkpoint 1 (0 ms, after say (user=100, text=tp) at 0 ms), 1 checkpoint(s) differ in all:

- users: 100: python [5, 6] turbo [0, 9]

### `backend/tests/test_engine.py::test_visitor_view_example_shows_each_effect#0` (differs)

Notes: random draws.

Boxes: `wf_act_give_var`, `wf_act_move_rotate_user`, `wf_act_rel_mov`, `wf_act_set_highlight`, `wf_act_set_visibility`, `wf_act_show_message`, `wf_act_toggle_state`, `wf_floor_switch1`, `wf_trg_click_furni`, `wf_trg_says_something`, `wf_trg_state_changed`, `wf_var_user`, `wf_xtra_rotate_to_dir`, `wf_xtra_varfx_number`

First difference at checkpoint 7 (700 ms, after say (user=500, text=hp) at 600 ms), 5 checkpoint(s) differ in all:

- variables: hp on user:500: python 40 turbo -

### `backend/tests/test_engine.py::test_a_named_bot_walks_to_furni_and_fires_bot_reached_furni#0` (differs, known cause)

Cause: Open, needs a Habbo capture: Turbo walks a bot one step per avatar cycle from the next cycle and is a step short at 1.6 s; Python's bot is there already.

Boxes: `wf_act_bot_move`, `wf_act_log`, `wf_trg_bot_reached_stf`, `wf_trg_says_something`

First difference at checkpoint 1 (1600 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- users: 200: python [3, 0] turbo [2, 0]

### `backend/tests/test_engine.py::test_background_toner_colour_switching_and_smart_variables#0` (differs, known cause)

Notes: inputs Turbo does not replay: toner.

Cause: The replay's: the test gives the user rights by editing the engine, which no input records, and sets toner colours, which the replay does not send; Turbo's user may switch the toner from the start.

Boxes: `wf_act_change_var_val`, `wf_trg_says_something`

First difference at checkpoint 1 (0 ms, after use (user=100, furni=50) at 0 ms), 6 checkpoint(s) differ in all:

- furni: 50: python [3, 3, 0, 0] turbo [3, 3, 0, 1]

### `backend/tests/test_engine.py::test_bot_follows_a_user_and_fires_reached_user_once_it_catches_up#0` (differs, known cause)

Cause: Open, needs a Habbo capture: Turbo's bot goes to the first free side of the user in the order north, east, south, west (here east, walking through the user); Python's stops on the nearest side.

Boxes: `wf_act_bot_follow_avatar`, `wf_act_log`, `wf_trg_bot_reached_avtr`, `wf_trg_says_something`

First difference at checkpoint 1 (3000 ms, after say (user=100, text=follow) at 0 ms), 2 checkpoint(s) differ in all:

- users: 200: python [3, 0] turbo [4, 0]

### `backend/tests/test_engine.py::test_bot_gives_a_hand_item_and_talks#0` (differs, known cause)

Cause: Open, needs a Habbo capture: Turbo's bot goes to the first free side of the user in the order north, east, south, west (here east, walking through the user); Python's stops on the nearest side.

Boxes: `wf_act_bot_give_handitem`, `wf_act_bot_talk`, `wf_act_bot_talk_to_avatar`, `wf_trg_says_something`

First difference at checkpoint 1 (3000 ms, after say (user=100, text=drink) at 0 ms), 2 checkpoint(s) differ in all:

- users: 200: python [3, 0] turbo [5, 0]

### `backend/tests/test_engine.py::test_defined_variables_are_listed_until_something_holds_them#0` (differs, known cause)

Cause: The replay's: the API write is to a user who is not in the room (user:1), which the replay does not send; Turbo would keep it for the absent player, out of the room's sight.

Boxes: `wf_var_context`, `wf_var_user`

First difference at checkpoint 1 (0 ms, after api_set (variable=score, key=user:1, value=5) at 0 ms), 1 checkpoint(s) differ in all:

- variables: score on user:1: python 5 turbo -

### `backend/tests/test_engine.py::test_leaving_without_standing_loses_up_to_ten_seconds#0` (differs, known cause)

Cause: Python is off: it keeps a user's room-active variables after the user leaves; in Habbo an active user variable goes with the user, and Turbo drops the user's store when they leave.

Boxes: `wf_act_change_var_val`, `wf_act_give_var`, `wf_act_remove_var`, `wf_act_send_signal`, `wf_antenna1`, `wf_antenna2`, `wf_cnd_has_var`, `wf_cnd_not_trggrer_on`, `wf_cnd_trggrer_on_frn`, `wf_slc_users_with_var`, `wf_trg_periodically`, `wf_trg_recv_signal`, `wf_trg_says_something`, `wf_trg_walks_off_furni`, `wf_trg_walks_on_furni`, `wf_var_user`, `wf_xtra_exec_in_order`, `wf_xtra_var_time_util`

First difference at checkpoint 2 (79000 ms, after leave (user=500) at 19000 ms), 1 checkpoint(s) differ in all:

- variables: last_duty on user:500: python 1700000000 turbo -
- variables: on_duty on user:500: python 0 turbo -
- variables: seconds on user:500: python 10 turbo -
- variables: tmp on user:500: python 10 turbo -

### `backend/tests/test_engine.py::test_place_and_remove_temporary_furni#0` (differs, known cause)

Cause: Python is off: it copies any furni; Habbo lets Place Temporary Furni copy only Builders Club furni (official client capture: the player's own chair refused with furni_can_not_be_cloned), so Turbo refused the box's settings and placed nothing.

Boxes: `wf_act_place_furni`, `wf_act_remove_furni`, `wf_slc_furni_area`, `wf_trg_says_something`

Turbo refused the settings of: `wf_act_place_furni`

First difference at checkpoint 1 (10 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- furni: 61: python [8, 8, 0, 0] turbo None

### `backend/tests/test_engine.py::test_value_can_come_from_another_variable#0` (differs, known cause)

Cause: Python is off: an API write stores a number on a variable whose 'has value' is off; Habbo keeps only that it is held, as Turbo does (RoomWiredSystem.WebApi: 'the number sent is not kept').

Boxes: `wf_act_give_var`, `wf_act_log`, `wf_cnd_var_val_match`, `wf_trg_says_something`, `wf_var_room`, `wf_var_user`, `wf_xtra_exec_in_order`

First difference at checkpoint 1 (0 ms, after api_set (variable=base, key=user:100, value=9) at 0 ms), 6 checkpoint(s) differ in all:

- variables: base on user:100: python 9 turbo 1

### `backend/tests/test_engine.py::test_variable_age_can_measure_from_the_last_change#0` (differs, known cause)

Cause: Python is off: an API write stores a number on a variable whose 'has value' is off; Habbo keeps only that it is held, as Turbo does (RoomWiredSystem.WebApi: 'the number sent is not kept').

Boxes: `wf_act_log`, `wf_cnd_var_age_match`, `wf_trg_says_something`, `wf_var_user`

First difference at checkpoint 2 (5000 ms, after api_set (variable=role, key=user:100, value=2) at 5000 ms), 2 checkpoint(s) differ in all:

- variables: role on user:100: python 2 turbo 1

### `backend/tests/test_engine.py::test_variable_age_can_measure_from_the_last_change#1` (differs, known cause)

Cause: Python is off: an API write stores a number on a variable whose 'has value' is off; Habbo keeps only that it is held, as Turbo does (RoomWiredSystem.WebApi: 'the number sent is not kept').

Boxes: `wf_act_log`, `wf_cnd_var_age_match`, `wf_trg_says_something`, `wf_var_user`

First difference at checkpoint 2 (5000 ms, after api_set (variable=role, key=user:100, value=2) at 5000 ms), 2 checkpoint(s) differ in all:

- variables: role on user:100: python 2 turbo 1

### `backend/tests/test_engine.py::test_a_new_variable_has_no_old_value_and_a_team_type_uses_real_numbers#0` (differs, Turbo is the reference)

Cause: Turbo is the reference: built-in variables and placeholders.

Boxes: `wf_act_give_var`, `wf_act_show_message`, `wf_trg_says_something`, `wf_trg_var_changed`, `wf_var_user`, `wf_xtra_text_output_variable`

First difference at checkpoint 1 (500 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- messages: python only: 'old null diff null'
- messages: turbo only: 'old $(o) diff $(d)'

### `backend/tests/test_engine.py::test_built_in_variables_in_selectors_and_placeholders#0` (differs, Turbo is the reference)

Cause: Turbo is the reference: built-in variables and placeholders.

Boxes: `wf_act_show_message`, `wf_slc_users_with_var`, `wf_trg_says_something`, `wf_xtra_text_output_variable`

First difference at checkpoint 1 (0 ms, after say (user=100, text=go) at 0 ms), 2 checkpoint(s) differ in all:

- messages: python only: 'at 7'
- messages: turbo only: 'at $(x)'

### `backend/tests/test_engine.py::test_built_in_variables_read_the_room#0` (differs, Turbo is the reference)

Cause: Turbo is the reference: built-in variables and placeholders.

Boxes: `wf_act_show_message`, `wf_cnd_var_val_match`, `wf_trg_says_something`

First difference at checkpoint 1 (500 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- messages: python only: 'all true'

### `backend/tests/test_engine.py::test_event_values_reach_stacks_set_off_by_a_change#0` (differs, Turbo is the reference)

Cause: Turbo is the reference: built-in variables and placeholders.

Boxes: `wf_act_give_var`, `wf_act_show_message`, `wf_trg_says_something`, `wf_trg_var_changed`, `wf_var_user`, `wf_xtra_text_output_variable`

First difference at checkpoint 1 (500 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- messages: python only: '0 to 5'
- messages: turbo only: '$(t) to $(n)'

### `backend/tests/test_engine.py::test_placeholders_and_text_connector#0` (differs, Turbo is the reference)

Notes: settings the client's params cannot carry: wf_xtra_var_text_connector.

Cause: Turbo is the reference: built-in variables and placeholders.

Boxes: `wf_act_give_var`, `wf_act_show_message`, `wf_trg_says_something`, `wf_xtra_exec_in_order`, `wf_xtra_text_output_username`, `wf_xtra_text_output_variable`, `wf_xtra_var_text_connector`

First difference at checkpoint 1 (0 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- messages: python only: 'Ann has carrot $(unknown)'
- messages: turbo only: 'Ann has $(thing) $(unknown)'

### `backend/tests/test_engine.py::test_placeholders_read_room_and_context_values#0` (differs, Turbo is the reference)

Cause: Turbo is the reference: built-in variables and placeholders.

Boxes: `wf_act_show_message`, `wf_slc_users_area`, `wf_trg_says_something`, `wf_xtra_text_output_variable`

First difference at checkpoint 1 (500 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- messages: python only: '1 and 1'
- messages: turbo only: '$(n) and $(s)'

### `backend/tests/test_engine.py::test_writable_built_ins_can_be_changed[@position.x-7-user-extra1-<lambda>]#0` (differs, Turbo is the reference)

Cause: Turbo is the reference: built-in variables and placeholders.

Boxes: `wf_act_change_var_val`, `wf_trg_says_something`

First difference at checkpoint 1 (1000 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- users: 100: python [7, 9] turbo [0, 9]

### `backend/tests/test_engine.py::test_writable_built_ins_can_be_changed[@position.y-8-furni-extra5-<lambda>]#0` (differs, Turbo is the reference)

Cause: Turbo is the reference: built-in variables and placeholders.

Boxes: `wf_act_change_var_val`, `wf_trg_says_something`

First difference at checkpoint 1 (1000 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- furni: 50: python [5, 8, 0, 0] turbo [5, 5, 0, 0]

### `backend/tests/test_engine.py::test_writable_built_ins_can_be_changed[@rotation-4-furni-extra2-<lambda>]#0` (differs, Turbo is the reference)

Cause: Turbo is the reference: built-in variables and placeholders.

Boxes: `wf_act_change_var_val`, `wf_trg_says_something`

First difference at checkpoint 1 (1000 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- furni: 50: python [5, 5, 4, 0] turbo [5, 5, 0, 0]

### `backend/tests/test_engine.py::test_writable_built_ins_can_be_changed[@state-1-furni-extra4-<lambda>]#0` (differs, Turbo is the reference)

Cause: Turbo is the reference: built-in variables and placeholders.

Boxes: `wf_act_change_var_val`, `wf_trg_says_something`

First difference at checkpoint 1 (1000 ms, after say (user=100, text=go) at 0 ms), 1 checkpoint(s) differ in all:

- furni: 50: python [5, 5, 0, 1] turbo [5, 5, 0, 0]

## Scenarios that match

- `backend/tests/test_engine.py::test_a_box_edited_during_a_run_uses_its_new_settings#0`
- `backend/tests/test_engine.py::test_a_called_stack_runs_its_plain_effects_and_not_its_negative_ones#0`
- `backend/tests/test_engine.py::test_a_counter_counts_up_in_half_seconds_and_shows_seconds#0`
- `backend/tests/test_engine.py::test_a_detail_can_be_put_down_and_the_room_state_shows_it#0`
- `backend/tests/test_engine.py::test_a_filter_alone_selects_nobody#0`
- `backend/tests/test_engine.py::test_a_floor_switch_is_for_anyone_standing_next_to_it#0`
- `backend/tests/test_engine.py::test_a_floor_switch_is_for_anyone_standing_next_to_it#1`
- `backend/tests/test_engine.py::test_a_game_counter_runs_the_game#0`
- `backend/tests/test_engine.py::test_a_global_change_needs_no_user#0`
- `backend/tests/test_engine.py::test_a_global_reads_zero_before_anything_sets_it#0`
- `backend/tests/test_engine.py::test_a_look_with_no_audience_does_nothing#0`
- `backend/tests/test_engine.py::test_a_move_by_hand_stays_in_the_room#0`
- `backend/tests/test_engine.py::test_a_move_without_the_add_on_is_no_flight#0`
- `backend/tests/test_engine.py::test_a_neighbourhood_centre_can_be_moved#0`
- `backend/tests/test_engine.py::test_a_new_variable_has_no_old_value_and_a_team_type_uses_real_numbers#1`
- `backend/tests/test_engine.py::test_a_new_variable_has_no_old_value_and_a_team_type_uses_real_numbers#2`
- `backend/tests/test_engine.py::test_a_new_variable_has_no_old_value_and_a_team_type_uses_real_numbers#3`
- `backend/tests/test_engine.py::test_a_projectile_turns_the_furni_and_the_shooter#0`
- `backend/tests/test_engine.py::test_a_seated_user_faces_the_way_the_seat_is_turned#0`
- `backend/tests/test_engine.py::test_a_signal_forwards_the_selected_users_in_one_signal_unless_split#0`
- `backend/tests/test_engine.py::test_a_signal_forwards_the_selected_users_in_one_signal_unless_split#1`
- `backend/tests/test_engine.py::test_a_signal_forwards_the_selected_users_in_one_signal_unless_split#2`
- `backend/tests/test_engine.py::test_a_state_the_furni_lacks_returns_to_its_first#0`
- `backend/tests/test_engine.py::test_a_team_score_never_goes_below_zero#0`
- `backend/tests/test_engine.py::test_a_user_already_seated_when_the_room_starts_is_not_an_action#0`
- `backend/tests/test_engine.py::test_a_user_with_rights_moves_furni_and_changes_boxes_during_a_run[details0]#0`
- `backend/tests/test_engine.py::test_a_user_with_rights_moves_furni_and_changes_boxes_during_a_run[details1]#0`
- `backend/tests/test_engine.py::test_a_value_set_by_hand_changes_it_and_fires_variable_changed#0`
- `backend/tests/test_engine.py::test_a_variable_box_draws_at_most_five_fx#0`
- `backend/tests/test_engine.py::test_adjusting_does_not_fire_the_time_trigger_but_counting_does#0`
- `backend/tests/test_engine.py::test_altitude_quantity_and_team_rank_conditions#0`
- `backend/tests/test_engine.py::test_altitude_quantity_and_team_rank_conditions#1`
- `backend/tests/test_engine.py::test_altitude_quantity_and_team_rank_conditions#2`
- `backend/tests/test_engine.py::test_altitude_quantity_and_team_rank_conditions#3`
- `backend/tests/test_engine.py::test_altitude_stays_within_the_room#0`
- `backend/tests/test_engine.py::test_an_action_runs_its_trigger_and_a_sign_number_must_match#0`
- `backend/tests/test_engine.py::test_area_selectors_cover_their_rectangle#0`
- `backend/tests/test_engine.py::test_arithmetic_edges#0`
- `backend/tests/test_engine.py::test_bad_altitude_settings_never_raise#0`
- `backend/tests/test_engine.py::test_bad_box_edits_are_ignored[3]#0`
- `backend/tests/test_engine.py::test_bad_box_edits_are_ignored[None]#0`
- `backend/tests/test_engine.py::test_bad_box_edits_are_ignored[bad]#0`
- `backend/tests/test_engine.py::test_bad_box_edits_are_ignored[settings3]#0`
- `backend/tests/test_engine.py::test_bad_settings_never_raise[settings0]#0`
- `backend/tests/test_engine.py::test_bad_settings_never_raise[settings10]#0`
- `backend/tests/test_engine.py::test_bad_settings_never_raise[settings1]#0`
- `backend/tests/test_engine.py::test_bad_settings_never_raise[settings2]#0`
- `backend/tests/test_engine.py::test_bad_settings_never_raise[settings3]#0`
- `backend/tests/test_engine.py::test_bad_settings_never_raise[settings4]#0`
- `backend/tests/test_engine.py::test_bad_settings_never_raise[settings5]#0`
- `backend/tests/test_engine.py::test_bad_settings_never_raise[settings8]#0`
- `backend/tests/test_engine.py::test_bad_settings_never_raise[settings9]#0`
- `backend/tests/test_engine.py::test_bot_teleport_effect_timing_and_clothes#0`
- `backend/tests/test_engine.py::test_built_in_variables_cannot_be_written_and_unknown_ones_read_as_absent#0`
- `backend/tests/test_engine.py::test_built_ins_from_the_catalogue_and_room#0`
- `backend/tests/test_engine.py::test_call_stacks_ignores_conditions_and_trigger#0`
- `backend/tests/test_engine.py::test_carry_toggle_previous_owner_only_and_multiple_placeholders#0`
- `backend/tests/test_engine.py::test_carry_toggle_previous_owner_only_and_multiple_placeholders#1`
- `backend/tests/test_engine.py::test_carry_toggle_previous_owner_only_and_multiple_placeholders#2`
- `backend/tests/test_engine.py::test_carry_toggle_previous_owner_only_and_multiple_placeholders#3`
- `backend/tests/test_engine.py::test_carry_users_moves_who_stands_on_the_furni#0`
- `backend/tests/test_engine.py::test_carry_users_moves_who_stands_on_the_furni#1`
- `backend/tests/test_engine.py::test_changing_a_variable_nobody_has_is_reported_not_created#0`
- `backend/tests/test_engine.py::test_chase_steps_toward_a_user_in_line_and_collides_next_to_them#0`
- `backend/tests/test_engine.py::test_clicking_a_user_selects_them_and_turns_the_clicker#0`
- `backend/tests/test_engine.py::test_clicking_an_invisible_click_tile_runs_click_tile#0`
- `backend/tests/test_engine.py::test_clock_commands#0`
- `backend/tests/test_engine.py::test_clock_does_not_drift_over_a_long_shift#0`
- `backend/tests/test_engine.py::test_conditions_and_removal_follow_a_furni_variable#0`
- `backend/tests/test_engine.py::test_conditions_block_and_or_eval_relaxes#0`
- `backend/tests/test_engine.py::test_conditions_block_and_or_eval_relaxes#1`
- `backend/tests/test_engine.py::test_context_variables_last_one_run#0`
- `backend/tests/test_engine.py::test_curve_strength_from_a_variable_and_none_when_nobody_holds_it#0`
- `backend/tests/test_engine.py::test_curve_strength_from_a_variable_and_none_when_nobody_holds_it#1`
- `backend/tests/test_engine.py::test_date_time_and_range_conditions#0`
- `backend/tests/test_engine.py::test_date_time_and_range_conditions#1`
- `backend/tests/test_engine.py::test_date_time_and_range_conditions#2`
- `backend/tests/test_engine.py::test_date_time_and_range_conditions#3`
- `backend/tests/test_engine.py::test_date_time_and_range_conditions#4`
- `backend/tests/test_engine.py::test_date_time_and_range_conditions#5`
- `backend/tests/test_engine.py::test_date_time_and_range_conditions#6`
- `backend/tests/test_engine.py::test_date_time_and_range_conditions#7`
- `backend/tests/test_engine.py::test_default_user_source_ignores_a_selector#0`
- `backend/tests/test_engine.py::test_delay_counts_half_seconds#0`
- `backend/tests/test_engine.py::test_echo_reads_and_writes_the_variable_it_echoes#0`
- `backend/tests/test_engine.py::test_execute_in_order_runs_bottom_up_and_default_order_varies#0`
- `backend/tests/test_engine.py::test_execute_in_order_runs_bottom_up_and_default_order_varies#1`
- `backend/tests/test_engine.py::test_execute_in_order_runs_bottom_up_and_default_order_varies#2`
- `backend/tests/test_engine.py::test_execute_in_order_runs_bottom_up_and_default_order_varies#3`
- `backend/tests/test_engine.py::test_execute_in_order_runs_bottom_up_and_default_order_varies#4`
- `backend/tests/test_engine.py::test_execute_in_order_runs_bottom_up_and_default_order_varies#5`
- `backend/tests/test_engine.py::test_execute_in_order_runs_bottom_up_and_default_order_varies#6`
- `backend/tests/test_engine.py::test_execute_in_order_runs_bottom_up_and_default_order_varies#7`
- `backend/tests/test_engine.py::test_execute_in_order_runs_bottom_up_and_default_order_varies#8`
- `backend/tests/test_engine.py::test_execute_in_order_runs_from_the_bottom_up#0`
- `backend/tests/test_engine.py::test_execution_limit_addon#0`
- `backend/tests/test_engine.py::test_filter_furni_by_variable_keeps_the_highest_values#0`
- `backend/tests/test_engine.py::test_flee_steps_away_and_keeps_its_way_when_nobody_is_near#0`
- `backend/tests/test_engine.py::test_freeze_stops_walking_until_unfrozen_or_a_wired_teleport#0`
- `backend/tests/test_engine.py::test_furious_room_cannot_hang_the_server#0`
- `backend/tests/test_engine.py::test_furni_area_and_altitude#0`
- `backend/tests/test_engine.py::test_furni_area_and_altitude#1`
- `backend/tests/test_engine.py::test_furni_area_and_altitude#2`
- `backend/tests/test_engine.py::test_furni_area_and_altitude#3`
- `backend/tests/test_engine.py::test_furni_on_furni_follows_the_pile#0`
- `backend/tests/test_engine.py::test_furni_on_furni_follows_the_pile#1`
- `backend/tests/test_engine.py::test_furni_on_furni_follows_the_pile#2`
- `backend/tests/test_engine.py::test_furni_on_furni_follows_the_pile#3`
- `backend/tests/test_engine.py::test_furni_to_furni_moves_the_triggering_furni_onto_the_target#0`
- `backend/tests/test_engine.py::test_furni_to_user_uses_the_first_user#0`
- `backend/tests/test_engine.py::test_furni_triggers_only_fire_for_their_picks#0`
- `backend/tests/test_engine.py::test_furni_variables_are_given_to_picked_furni#0`
- `backend/tests/test_engine.py::test_game_triggers_fire#0`
- `backend/tests/test_engine.py::test_give_and_remove_variable_add_a_hand_item_by_hand#0`
- `backend/tests/test_engine.py::test_give_and_remove_variable_add_a_hand_item_by_hand#1`
- `backend/tests/test_engine.py::test_give_variable_gives_nothing_when_its_source_is_empty#0`
- `backend/tests/test_engine.py::test_give_without_overwrite_keeps_value_and_timestamp#0`
- `backend/tests/test_engine.py::test_global_variables_have_one_value#0`
- `backend/tests/test_engine.py::test_hand_item_action_and_direction_conditions#0`
- `backend/tests/test_engine.py::test_hand_item_action_and_direction_conditions#1`
- `backend/tests/test_engine.py::test_hand_item_action_and_direction_conditions#2`
- `backend/tests/test_engine.py::test_hand_item_action_and_direction_conditions#3`
- `backend/tests/test_engine.py::test_hand_item_action_and_direction_conditions#4`
- `backend/tests/test_engine.py::test_hand_item_action_and_direction_conditions#5`
- `backend/tests/test_engine.py::test_hand_item_action_and_direction_conditions#6`
- `backend/tests/test_engine.py::test_hand_item_is_writable#0`
- `backend/tests/test_engine.py::test_hand_item_is_writable#1`
- `backend/tests/test_engine.py::test_hidden_messages_stay_out_of_the_room_chat_and_bots_count_as_bots#0`
- `backend/tests/test_engine.py::test_highlight_and_visibility_reach_furni_and_users#0`
- `backend/tests/test_engine.py::test_highlight_and_visibility_record_their_easing#0`
- `backend/tests/test_engine.py::test_invert_selects_what_did_not_match#0`
- `backend/tests/test_engine.py::test_join_and_leave_team#0`
- `backend/tests/test_engine.py::test_keyword_matching#0`
- `backend/tests/test_engine.py::test_keyword_syncs_at_once_only_while_on_duty#0`
- `backend/tests/test_engine.py::test_keyword_types[settings0-oh hello there you-True]#0`
- `backend/tests/test_engine.py::test_keyword_types[settings1-shello therefore-True]#0`
- `backend/tests/test_engine.py::test_keyword_types[settings2-oh hello there you-False]#0`
- `backend/tests/test_engine.py::test_keyword_types[settings3-Hello There-True]#0`
- `backend/tests/test_engine.py::test_keyword_types[settings4-something else entirely-True]#0`
- `backend/tests/test_engine.py::test_keyword_types[settings5-oh hello there you-False]#0`
- `backend/tests/test_engine.py::test_keyword_types[settings6-hello there-True]#0`
- `backend/tests/test_engine.py::test_link_messages_carry_the_trigger_text_or_a_custom_message#0`
- `backend/tests/test_engine.py::test_link_messages_carry_the_trigger_text_or_a_custom_message#1`
- `backend/tests/test_engine.py::test_move_furni_as_group_keeps_the_layout#0`
- `backend/tests/test_engine.py::test_move_rotate_takes_diagonals#0`
- `backend/tests/test_engine.py::test_move_to_direction_turns_when_blocked_and_a_user_in_the_way_collides#0`
- `backend/tests/test_engine.py::test_move_user_walks_and_turns#0`
- `backend/tests/test_engine.py::test_move_user_walks_and_turns#1`
- `backend/tests/test_engine.py::test_movement_physics_blocks_moves_through_users_and_lands_on_top#0`
- `backend/tests/test_engine.py::test_movement_physics_blocks_moves_through_users_and_lands_on_top#1`
- `backend/tests/test_engine.py::test_movement_physics_blocks_moves_through_users_and_lands_on_top#2`
- `backend/tests/test_engine.py::test_movement_physics_blocks_moves_through_users_and_lands_on_top#3`
- `backend/tests/test_engine.py::test_negative_delays_are_milliseconds_and_all_delays_are_capped[-50-50]#0`
- `backend/tests/test_engine.py::test_negative_delays_are_milliseconds_and_all_delays_are_capped[-650-650]#0`
- `backend/tests/test_engine.py::test_negative_delays_are_milliseconds_and_all_delays_are_capped[-90000-60000]#0`
- `backend/tests/test_engine.py::test_negative_delays_are_milliseconds_and_all_delays_are_capped[900-300000]#0`
- `backend/tests/test_engine.py::test_negative_effects_run_only_when_conditions_fail#0`
- `backend/tests/test_engine.py::test_negative_effects_run_only_when_conditions_fail#1`
- `backend/tests/test_engine.py::test_old_flights_are_dropped#0`
- `backend/tests/test_engine.py::test_periods_and_limit_windows_can_be_half_seconds#0`
- `backend/tests/test_engine.py::test_plain_moves_send_no_flight_and_the_animation_add_ons_do#0`
- `backend/tests/test_engine.py::test_plain_moves_send_no_flight_and_the_animation_add_ons_do#1`
- `backend/tests/test_engine.py::test_plain_moves_send_no_flight_and_the_animation_add_ons_do#2`
- `backend/tests/test_engine.py::test_plain_moves_send_no_flight_and_the_animation_add_ons_do#3`
- `backend/tests/test_engine.py::test_pointer_reads_the_box_its_accessor_holds_and_writes_change_nothing#0`
- `backend/tests/test_engine.py::test_points_only_count_during_a_game#0`
- `backend/tests/test_engine.py::test_projectile_options#0`
- `backend/tests/test_engine.py::test_projectile_options#1`
- `backend/tests/test_engine.py::test_projectile_options#2`
- `backend/tests/test_engine.py::test_projectile_options#3`
- `backend/tests/test_engine.py::test_projectile_options#4`
- `backend/tests/test_engine.py::test_random_and_unseen_addons#0`
- `backend/tests/test_engine.py::test_random_and_unseen_addons#1`
- `backend/tests/test_engine.py::test_random_picks_several_and_skips_recent_effects#0`
- `backend/tests/test_engine.py::test_random_picks_several_and_skips_recent_effects#1`
- `backend/tests/test_engine.py::test_random_rotation_turns_furni_and_replays#0`
- `backend/tests/test_engine.py::test_read_only_built_ins_cannot_be_changed#0`
- `backend/tests/test_engine.py::test_relative_move_stops_at_the_edge_and_at_users#0`
- `backend/tests/test_engine.py::test_relative_move_stops_at_the_edge_and_at_users#1`
- `backend/tests/test_engine.py::test_relative_move_stops_at_the_edge_and_at_users#2`
- `backend/tests/test_engine.py::test_replay_gives_the_same_result#0`
- `backend/tests/test_engine.py::test_replay_gives_the_same_result#1`
- `backend/tests/test_engine.py::test_same_seed_same_random#0`
- `backend/tests/test_engine.py::test_same_seed_same_random#1`
- `backend/tests/test_engine.py::test_score_achieved_runs_once_as_a_team_passes_the_mark#0`
- `backend/tests/test_engine.py::test_selector_with_no_match_affects_nobody_not_the_triggerer#0`
- `backend/tests/test_engine.py::test_selectors_add_up_and_filters_narrow_wherever_they_stand#0`
- `backend/tests/test_engine.py::test_selectors_add_up_and_filters_narrow_wherever_they_stand#1`
- `backend/tests/test_engine.py::test_selectors_add_up_and_filters_narrow_wherever_they_stand#2`
- `backend/tests/test_engine.py::test_selectors_and_filters#0`
- `backend/tests/test_engine.py::test_selectors_and_filters#1`
- `backend/tests/test_engine.py::test_set_altitude[lower-0.5]#0`
- `backend/tests/test_engine.py::test_set_altitude[raise-2.5]#0`
- `backend/tests/test_engine.py::test_set_altitude[set-1.0]#0`
- `backend/tests/test_engine.py::test_short_period_runs_at_its_own_speed_and_stops_at_a_minimum#0`
- `backend/tests/test_engine.py::test_short_period_runs_at_its_own_speed_and_stops_at_a_minimum#1`
- `backend/tests/test_engine.py::test_signal_loop_stops_at_the_limit#0`
- `backend/tests/test_engine.py::test_sitting_lying_and_standing_up_are_actions#0`
- `backend/tests/test_engine.py::test_sitting_marks_user_on_duty#0`
- `backend/tests/test_engine.py::test_standing_up_banks_the_time_and_ends_the_shift#0`
- `backend/tests/test_engine.py::test_team_condition_and_selector[any-True]#0`
- `backend/tests/test_engine.py::test_team_condition_and_selector[any-True]#1`
- `backend/tests/test_engine.py::test_team_condition_and_selector[blue-True]#0`
- `backend/tests/test_engine.py::test_team_condition_and_selector[blue-True]#1`
- `backend/tests/test_engine.py::test_team_condition_and_selector[red-False]#0`
- `backend/tests/test_engine.py::test_team_condition_and_selector[red-False]#1`
- `backend/tests/test_engine.py::test_team_has_score[equal-9-True]#0`
- `backend/tests/test_engine.py::test_team_has_score[less-10-True]#0`
- `backend/tests/test_engine.py::test_team_has_score[more-9-False]#0`
- `backend/tests/test_engine.py::test_the_furni_name_placeholder_uses_the_public_name#0`
- `backend/tests/test_engine.py::test_the_neighbourhood_selectors_pick_what_is_around_the_user#0`
- `backend/tests/test_engine.py::test_time_is_banked_every_ten_seconds_while_seated#0`
- `backend/tests/test_engine.py::test_timer_triggers_and_conditions#0`
- `backend/tests/test_engine.py::test_toggle_leaves_floor_switches_alone#0`
- `backend/tests/test_engine.py::test_toggle_state_and_state_trigger#0`
- `backend/tests/test_engine.py::test_trace_is_capped#0`
- `backend/tests/test_engine.py::test_two_shifts_add_up#0`
- `backend/tests/test_engine.py::test_unknown_boxes_are_stubs_and_are_logged#0`
- `backend/tests/test_engine.py::test_users_by_action_selects_who_is_waving_for_five_seconds#0`
- `backend/tests/test_engine.py::test_users_by_type_finds_only_habbos_in_a_sandbox#0`
- `backend/tests/test_engine.py::test_users_by_type_finds_only_habbos_in_a_sandbox#1`
- `backend/tests/test_engine.py::test_users_by_type_finds_only_habbos_in_a_sandbox#2`
- `backend/tests/test_engine.py::test_users_with_a_hand_item_are_selected#0`
- `backend/tests/test_engine.py::test_using_furni_loops_through_its_states#0`
- `backend/tests/test_engine.py::test_using_furni_loops_through_its_states#1`
- `backend/tests/test_engine.py::test_using_furni_loops_through_its_states#2`
- `backend/tests/test_engine.py::test_using_furni_loops_through_its_states#3`
- `backend/tests/test_engine.py::test_valid_moves_checks_the_stacks_moves_before_running#0`
- `backend/tests/test_engine.py::test_variable_age[settings0-1000-True]#0`
- `backend/tests/test_engine.py::test_variable_age[settings1-2000-False]#0`
- `backend/tests/test_engine.py::test_variable_age[settings2-2000-True]#0`
- `backend/tests/test_engine.py::test_variable_age[settings3-2001-True]#0`
- `backend/tests/test_engine.py::test_variable_age[settings4-59000-False]#0`
- `backend/tests/test_engine.py::test_variable_age[settings5-499-True]#0`
- `backend/tests/test_engine.py::test_variable_age_fails_when_nothing_holds_the_variable#0`
- `backend/tests/test_engine.py::test_variable_fx_only_shows_over_its_kind_of_holder#0`
- `backend/tests/test_engine.py::test_variable_fx_show_modes#0`
- `backend/tests/test_engine.py::test_variable_fx_show_modes#1`
- `backend/tests/test_engine.py::test_variable_fx_shows_the_variable_on_its_tile_over_each_holder#0`
- `backend/tests/test_engine.py::test_variable_value_condition_defaults_to_greater_than#0`
- `backend/tests/test_engine.py::test_walking_to_furni_needs_furni_a_user_can_stand_on#0`
- `backend/tests/test_engine.py::test_walking_turns_the_user_and_a_plain_move_does_not#0`
- `backend/tests/test_engine.py::test_without_rights_a_user_cannot_move_furni_or_change_boxes#0`
- `backend/tests/test_engine.py::test_writable_built_ins_can_be_changed[@altitude-150-furni-extra3-<lambda>]#0`
- `backend/tests/test_engine.py::test_writable_built_ins_can_be_changed[@direction-5-user-extra0-<lambda>]#0`
- `backend/tests/test_engine.py::test_writable_built_ins_can_be_changed[@teams.red.score-9-user-extra6-<lambda>]#0`
- `backend/tests/test_guide.py::test_score_counter_works#0`
- `backend/tests/test_guide.py::test_signal_relay_works#0`
- `backend/tests/test_guide.py::test_switch_flip_works#0`
