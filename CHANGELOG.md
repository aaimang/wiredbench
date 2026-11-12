# Changelog

From v0.12.0, Wiredbench is a Turbo plugin and its changes are in
[turbo-plugin/CHANGELOG.md](turbo-plugin/CHANGELOG.md). This file is the old web app's, up to v0.11.0.

## [0.11.0](https://github.com/aaimang/wiredbench/compare/v0.10.0...v0.11.0) (2026-11-09)


### Features

* bots and the nine bot boxes, hidden chat, a blocked avatar menu, and highlight and visibility easing ([#105](https://github.com/aaimang/wiredbench/issues/105)) ([bd31096](https://github.com/aaimang/wiredbench/commit/bd310961d12c34e15ad12eb8909ec4957709b856))
* eleven conditions, Valid Moves, Move as Group, Place/Remove Furni, Freeze, and working saved options ([#104](https://github.com/aaimang/wiredbench/issues/104)) ([5f8fd29](https://github.com/aaimang/wiredbench/commit/5f8fd29ca76fdccc4335bb3cbac99de03e44f8e4))
* movement add-ons (No Animation, Animation Time, Curve, Physics), Echo and Pointer variables, and Link messages ([#103](https://github.com/aaimang/wiredbench/issues/103)) ([67a6eb0](https://github.com/aaimang/wiredbench/commit/67a6eb09e23963f184da9407f772cd1b438d69ab))
* nine more WIRED boxes, no diagonal sitting, and a View-as teleport test ([#100](https://github.com/aaimang/wiredbench/issues/100)) ([ee6023e](https://github.com/aaimang/wiredbench/commit/ee6023e6d43bf284dd6a539c46f4c51a94c3c565))
* posture actions, Chase, Flee, Move to Direction, Collision, Click Tile and Furni Name ([#102](https://github.com/aaimang/wiredbench/issues/102)) ([0778497](https://github.com/aaimang/wiredbench/commit/0778497da44acb0e5e0dbe8fab5aeffd75b384d5))
* Room Background pictures and Background Toner colours, as in Habbo ([#107](https://github.com/aaimang/wiredbench/issues/107)) ([79934a1](https://github.com/aaimang/wiredbench/commit/79934a1caa5d8552e9f9401ddd6c80cdda5d2350))
* the Workspace furni list loads 60 more at a time ([#111](https://github.com/aaimang/wiredbench/issues/111)) ([905d720](https://github.com/aaimang/wiredbench/commit/905d720346181006929ed0488713d18bfdfc030a))
* vending machines hand the user a drink or other hand item ([#99](https://github.com/aaimang/wiredbench/issues/99)) ([ddf10c8](https://github.com/aaimang/wiredbench/commit/ddf10c87408e097ab7e81b7f90d62d1557f154ed))


### Bug Fixes

* avatars sink in water patches, and room backgrounds draw behind the room ([#106](https://github.com/aaimang/wiredbench/issues/106)) ([23c77df](https://github.com/aaimang/wiredbench/commit/23c77dfab8ca492334ac58d5bb546cf371d02f72))
* avatars sit in baths and stand on building blocks as in Habbo ([#112](https://github.com/aaimang/wiredbench/issues/112)) ([1373f95](https://github.com/aaimang/wiredbench/commit/1373f9505465a86130627025da3b4b0dc50d2304))
* avatars walk at 12 frames a second, as in Habbo's client ([#110](https://github.com/aaimang/wiredbench/issues/110)) ([bff6a07](https://github.com/aaimang/wiredbench/commit/bff6a07e2c3254c5b0d2794c9169a7631961f414))
* draw order, clicks and walking on furni work as in Habbo's client ([#108](https://github.com/aaimang/wiredbench/issues/108)) ([b1d125e](https://github.com/aaimang/wiredbench/commit/b1d125ed45cedac03754f276808a085485c69ddf))


### Documentation

* name 94 unnamed WIRED box positions from the client's setup forms ([#109](https://github.com/aaimang/wiredbench/issues/109)) ([a9606a9](https://github.com/aaimang/wiredbench/commit/a9606a9fa1fcf64fe449279a0fca1623e7e53ddc))

## [0.10.0](https://github.com/aaimang/wiredbench/compare/v0.9.1...v0.10.0) (2026-11-08)


### Features

* furni need rights to switch, and dice roll, as in a real room ([#95](https://github.com/aaimang/wiredbench/issues/95)) ([0a7e9d2](https://github.com/aaimang/wiredbench/commit/0a7e9d259195296a5ed3f800b026f4e9c00b53dc))
* room rights during a run, a theme toggle, more furni to place ([#92](https://github.com/aaimang/wiredbench/issues/92)) ([cb728f2](https://github.com/aaimang/wiredbench/commit/cb728f266a01cc7962fd7d46d8e42a824fc5e00d))
* teleports, one-way gates and gates work as in a room ([f2aa3cd](https://github.com/aaimang/wiredbench/commit/f2aa3cdce7ab52100c592eaf4d91c9a5891e872a))


### Bug Fixes

* lie on a bed's head row and sit between a seat's layers ([#96](https://github.com/aaimang/wiredbench/issues/96)) ([79915a6](https://github.com/aaimang/wiredbench/commit/79915a60612e5ed58e7ff91d7ad96d2831a832b8))
* sit and lie on furni as Habbo's client draws it ([#94](https://github.com/aaimang/wiredbench/issues/94)) ([bc29a15](https://github.com/aaimang/wiredbench/commit/bc29a15fc9d6382a2c241ba22c6a58a0c1efcb34))
* upgrade Debian packages in the image for the zlib CVEs ([5b11b82](https://github.com/aaimang/wiredbench/commit/5b11b826d62146acf8df7219e3c44a290ccfb954))

## [0.9.1](https://github.com/aaimang/wiredbench/compare/v0.9.0...v0.9.1) (2026-11-07)


### Bug Fixes

* floor shadow under avatars, grey out a kiss with an effect, projectile checked ([#90](https://github.com/aaimang/wiredbench/issues/90)) ([ffac719](https://github.com/aaimang/wiredbench/commit/ffac719e73253ec3f8ef762e27f5f619cb93d975))

## [0.9.0](https://github.com/aaimang/wiredbench/compare/v0.8.0...v0.9.0) (2026-11-08)

Wiredbench can now draw avatars itself, from Habbo's own client files, including avatar effects. View as user works much more like a real client, and rooms get time zones, avatar details, faces and actions.

### Avatars drawn by Wiredbench (beta)

Turn it on in **Settings → Avatar drawing**. Anything it cannot draw still comes from Habbo's image service.

* Draw avatars from their parts using Habbo's client rules: standing, walking, sitting, lying, actions, signs, faces and hand items ([#84](https://github.com/aaimang/wiredbench/pull/84), [#85](https://github.com/aaimang/wiredbench/pull/85))
* Draw avatar effects: ones that add layers around the avatar ([#81](https://github.com/aaimang/wiredbench/pull/81)), and ones that change the body, frame by frame ([#86](https://github.com/aaimang/wiredbench/pull/86)). Effects the room cannot draw are marked ([#83](https://github.com/aaimang/wiredbench/pull/83))
* Walking with an effect moves the legs and turns as it should, effects play their walking and sitting frames, and effect shadows are drawn ([#87](https://github.com/aaimang/wiredbench/pull/87))
* The Enchanted Broomstick draws in every direction without freezing, and variable displays sit just above the head ([#87](https://github.com/aaimang/wiredbench/pull/87))
* Blow kiss and respect play once at Habbo's own speed, keep their pace while walking, and an effect blocks a blow kiss. Skates and boards lift the avatar ([#87](https://github.com/aaimang/wiredbench/pull/87), [#88](https://github.com/aaimang/wiredbench/pull/88))

### View as user

* Select, use and chat as a client does, and walk onto a clicked chair or box ([#71](https://github.com/aaimang/wiredbench/pull/71), [#76](https://github.com/aaimang/wiredbench/pull/76))
* Show WIRED effects to visitors, update four times a second and animate moves ([#69](https://github.com/aaimang/wiredbench/pull/69), [#70](https://github.com/aaimang/wiredbench/pull/70))
* A `:wired` inspection window ([#68](https://github.com/aaimang/wiredbench/pull/68)), and the catalogue's furni facts, with `@is_stackable` ([#77](https://github.com/aaimang/wiredbench/pull/77))
* Keep the direction a visitor walked in, and skip old messages on entry ([#75](https://github.com/aaimang/wiredbench/pull/75), [#73](https://github.com/aaimang/wiredbench/pull/73))
* A visitor view test example room ([#72](https://github.com/aaimang/wiredbench/pull/72))

### Rooms and avatars

* Room time zones, with a list and a default zone, and a menu you can hide ([#58](https://github.com/aaimang/wiredbench/pull/58), [#62](https://github.com/aaimang/wiredbench/pull/62))
* Avatar details, actions, signs and faces in the user panel ([#58](https://github.com/aaimang/wiredbench/pull/58), [#63](https://github.com/aaimang/wiredbench/pull/63), [#65](https://github.com/aaimang/wiredbench/pull/65))
* Sliding and thrown furni are drawn on every frame ([#74](https://github.com/aaimang/wiredbench/pull/74))
* Nothing can be put on furni that cannot hold things, such as a chair ([#78](https://github.com/aaimang/wiredbench/pull/78))

### Fixes

* A sitting or lying avatar faces the way its seat is turned, and can turn for a moment before facing it again ([#79](https://github.com/aaimang/wiredbench/pull/79), [#80](https://github.com/aaimang/wiredbench/pull/80))
* Moving a seat away in Build stands the avatar up, facing the same way ([#89](https://github.com/aaimang/wiredbench/pull/89))
* Avatars keep moving and stepping while a new look, action or face loads ([#66](https://github.com/aaimang/wiredbench/pull/66), [#67](https://github.com/aaimang/wiredbench/pull/67))
* Hand items draw in every direction, and walking keeps its direction ([#64](https://github.com/aaimang/wiredbench/pull/64), [#60](https://github.com/aaimang/wiredbench/pull/60))
* Laughing no longer uses Habbo's broken laugh image ([#73](https://github.com/aaimang/wiredbench/pull/73))
* Run controls no longer lose clicks ([#61](https://github.com/aaimang/wiredbench/pull/61))

### Security

* Update the Python base image for an apt security fix ([#82](https://github.com/aaimang/wiredbench/pull/82))

## [0.8.0](https://github.com/aaimang/wiredbench/compare/v0.7.0...v0.8.0) (2026-11-01)


### Features

* act on the holder a variable belongs to ([#36](https://github.com/aaimang/wiredbench/issues/36)) ([fcbb1ce](https://github.com/aaimang/wiredbench/commit/fcbb1ceaa405ae17f032a4a0d3709d63fb4f7150))
* add more built-in variables, writes and a values panel ([#57](https://github.com/aaimang/wiredbench/issues/57)) ([4b1a437](https://github.com/aaimang/wiredbench/commit/4b1a4374088e069dbb3c00f06353c2771be17475))
* animate furni and show counter time ([#44](https://github.com/aaimang/wiredbench/issues/44)) ([5dc3381](https://github.com/aaimang/wiredbench/commit/5dc33812dcbf429e5ca006425d44dfc69da1646b))
* base box badges on real evidence and count furni apart ([#52](https://github.com/aaimang/wiredbench/issues/52)) ([b3111cb](https://github.com/aaimang/wiredbench/commit/b3111cb0084ff2cfe1b1698de0f473f7248faf51))
* combine selectors and simulate area, altitude and stacking ([#37](https://github.com/aaimang/wiredbench/issues/37)) ([b7e1565](https://github.com/aaimang/wiredbench/commit/b7e156505383ea955a7946282f2dcc6e8cf4456f))
* draw variable displays with the same elements as a real room ([#50](https://github.com/aaimang/wiredbench/issues/50)) ([efa026b](https://github.com/aaimang/wiredbench/commit/efa026b481128088581bca42afc720d0397eb309))
* edit values in the run panel and ignore answers after Stop ([#51](https://github.com/aaimang/wiredbench/issues/51)) ([b0af58a](https://github.com/aaimang/wiredbench/commit/b0af58a17be4430b17bcb8613b3baa6dcecc7ac8))
* label box options and run precise delays from real room dumps ([#29](https://github.com/aaimang/wiredbench/issues/29)) ([d4ea545](https://github.com/aaimang/wiredbench/commit/d4ea545b85d5bf794dafb9b302413acaa16e73d7))
* read built-in variables and carry users on signals as a real room does ([#56](https://github.com/aaimang/wiredbench/issues/56)) ([6d51754](https://github.com/aaimang/wiredbench/commit/6d517543595afa04515cee1266783676f95ecc5b))
* show variable displays and use picks when exporting ([#49](https://github.com/aaimang/wiredbench/issues/49)) ([c10d3e0](https://github.com/aaimang/wiredbench/commit/c10d3e0709515d2de9e5fbc187e2fe6f334807a6))
* simulate counters, game timers and team scores ([#43](https://github.com/aaimang/wiredbench/issues/43)) ([f9575be](https://github.com/aaimang/wiredbench/commit/f9575bec0dfbe2e302f3040c57cce15204ca8b06))
* simulate highlight, visibility and carrying users ([#47](https://github.com/aaimang/wiredbench/issues/47)) ([069932d](https://github.com/aaimang/wiredbench/commit/069932d201d6a8bfa56bf16587c21e976546af1e))
* simulate more furni and user movement boxes ([#38](https://github.com/aaimang/wiredbench/issues/38)) ([36385c6](https://github.com/aaimang/wiredbench/commit/36385c6a9787e50fad33a101b997f3734ecc9c46))
* simulate teams, score and game state ([#42](https://github.com/aaimang/wiredbench/issues/42)) ([c387177](https://github.com/aaimang/wiredbench/commit/c387177db46bb7ae2b88b64b00be591b2d418726))
* simulate the Projectile add-on ([#54](https://github.com/aaimang/wiredbench/issues/54)) ([84efd53](https://github.com/aaimang/wiredbench/commit/84efd532a05b303f5ccf1138d5d3c8eff4cac663))
* simulate the Variable Age condition ([#34](https://github.com/aaimang/wiredbench/issues/34)) ([1eed0b2](https://github.com/aaimang/wiredbench/commit/1eed0b22c674fdc0b997baed1c40399dfa1de352))
* support all 30 Change Variable Value operations ([#32](https://github.com/aaimang/wiredbench/issues/32)) ([f34133b](https://github.com/aaimang/wiredbench/commit/f34133b06e8b6d346edbaf887e355af9ada57a1e))
* take a variable box's value from another variable ([#35](https://github.com/aaimang/wiredbench/issues/35)) ([851d57f](https://github.com/aaimang/wiredbench/commit/851d57feb28e3b3230fc407f17486959b9da5595))
* use facts from real WIRED boxes for defaults and evidence ([#27](https://github.com/aaimang/wiredbench/issues/27)) ([168987c](https://github.com/aaimang/wiredbench/commit/168987c500978100ec772e61fb7e5fdffd20d93b))


### Bug Fixes

* always export the sections G-Presets needs ([#40](https://github.com/aaimang/wiredbench/issues/40)) ([080cc51](https://github.com/aaimang/wiredbench/commit/080cc513d14105e4825614291b3843dcf557f2cb))
* draw wired looks properly and apply box edits during a run ([#48](https://github.com/aaimang/wiredbench/issues/48)) ([00adfe9](https://github.com/aaimang/wiredbench/commit/00adfe991a2a956d71981982dc0b6bfc2e118cd3))
* give run clock ticks their own rate limit ([#46](https://github.com/aaimang/wiredbench/issues/46)) ([0fe689c](https://github.com/aaimang/wiredbench/commit/0fe689cb3f0dea4b67bd30ef15e0d9cfe4c86f48))
* keep looping furni layers visible ([#55](https://github.com/aaimang/wiredbench/issues/55)) ([ab8b0c2](https://github.com/aaimang/wiredbench/commit/ab8b0c295eb49c98d713ea52b3785f764d9a30fe))
* list defined variables before they are set and run short timers at their real speed ([#30](https://github.com/aaimang/wiredbench/issues/30)) ([5fd57dd](https://github.com/aaimang/wiredbench/commit/5fd57dd14be3d3c6259a7d477eec8f1190b8215d))
* match default sources and floor switches seen in a real room ([#39](https://github.com/aaimang/wiredbench/issues/39)) ([26b4c8c](https://github.com/aaimang/wiredbench/commit/26b4c8c32f21f649f8186bedbc5f367504755aa7))
* match negative effects, stack order and walking seen in a real room ([#53](https://github.com/aaimang/wiredbench/issues/53)) ([4b97c92](https://github.com/aaimang/wiredbench/commit/4b97c92f84662226468b256547f5529f215321d4))
* play furni transitions and use furni on double-click ([#45](https://github.com/aaimang/wiredbench/issues/45)) ([ea27614](https://github.com/aaimang/wiredbench/commit/ea27614f2e727caf3d5dd3e921798ec2f8d8a682))
* start global variables at 0, as a real room does ([#33](https://github.com/aaimang/wiredbench/issues/33)) ([5891aae](https://github.com/aaimang/wiredbench/commit/5891aaea3517b6be4e57d6f502918f0b6c6e7454))
* use rela_candle1 in tutorials and record room checks ([#41](https://github.com/aaimang/wiredbench/issues/41)) ([e576e4d](https://github.com/aaimang/wiredbench/commit/e576e4d6af7bf3e06762b29a4ab67889347fe6e6))
* write variable values as two words and name operation and comparison ([#31](https://github.com/aaimang/wiredbench/issues/31)) ([195fde9](https://github.com/aaimang/wiredbench/commit/195fde9b39748ccfd2c31c95ffbd6b51cdc4a00d))

## [0.7.0](https://github.com/aaimang/wiredbench/compare/v0.6.0...v0.7.0) (2026-10-31)


### Features

* add a stack checker to the room editor ([#21](https://github.com/aaimang/wiredbench/issues/21)) ([ce55167](https://github.com/aaimang/wiredbench/commit/ce5516724b45b44aacd85db49c236b41d350c104))


### Bug Fixes

* make the live check safer and test batches properly ([#24](https://github.com/aaimang/wiredbench/issues/24)) ([578e7f0](https://github.com/aaimang/wiredbench/commit/578e7f0288185418338d229e7d93ff5113c41906))
* match the mock API's errors to a real room ([#22](https://github.com/aaimang/wiredbench/issues/22)) ([98b2638](https://github.com/aaimang/wiredbench/commit/98b26383b7eb8856e578169548f87f2b31784e84))

## [0.6.0](https://github.com/aaimang/wiredbench/compare/v0.5.0...v0.6.0) (2026-10-31)


### Features

* read and write real option numbers for the first 17 boxes ([#18](https://github.com/aaimang/wiredbench/issues/18)) ([adbf57e](https://github.com/aaimang/wiredbench/commit/adbf57e88d86e373dc6c51cbe0825b3a838f42c6))
* track how far each WIRED box's options have been checked ([#20](https://github.com/aaimang/wiredbench/issues/20)) ([ee74a7b](https://github.com/aaimang/wiredbench/commit/ee74a7be34d4ca47cb115b3ad1c5ebb5b85e1707))

## [0.5.0](https://github.com/aaimang/wiredbench/compare/v0.4.0...v0.5.0) (2026-10-31)


### Features

* add a WIRED guide and example rooms ([#15](https://github.com/aaimang/wiredbench/issues/15)) ([27df64c](https://github.com/aaimang/wiredbench/commit/27df64c2a50fd11b2f842ec7ed15f24b7d75464a))
* add an avatar list with select, rename and remove ([#13](https://github.com/aaimang/wiredbench/issues/13)) ([2f3d481](https://github.com/aaimang/wiredbench/commit/2f3d481dfccf1c4386c12bb1d51ab47af3ac968a))
* add furni card, move mode, click outside and keyboard shortcuts ([#11](https://github.com/aaimang/wiredbench/issues/11)) ([cbf16b2](https://github.com/aaimang/wiredbench/commit/cbf16b292847bf25d3e34592c95220b9113deec8))
* import and export rooms as Wiredbench and G-Presets files ([#14](https://github.com/aaimang/wiredbench/issues/14)) ([18a26e0](https://github.com/aaimang/wiredbench/commit/18a26e0e17dd37d98d3f244dcf6ae1081a71f146))
* list and highlight picked furni, and add real box options ([#17](https://github.com/aaimang/wiredbench/issues/17)) ([02babd9](https://github.com/aaimang/wiredbench/commit/02babd928b80fc874a470c729cb6ef1c84d1ed8a))


### Bug Fixes

* send ETag on mock API read errors, as a real room does ([#16](https://github.com/aaimang/wiredbench/issues/16)) ([dce9f40](https://github.com/aaimang/wiredbench/commit/dce9f4098e45ba0fca07bc2d9833770688fbdae0))

## [0.4.0](https://github.com/aaimang/wiredbench/compare/v0.3.1...v0.4.0) (2026-10-31)


### Features

* add mock Web API, dashboard, view as user and more settings ([#9](https://github.com/aaimang/wiredbench/issues/9)) ([8c95600](https://github.com/aaimang/wiredbench/commit/8c95600cb86a6d8dc06f4e48c23c8aa370018e10))

## [0.3.1](https://github.com/aaimang/wiredbench/compare/v0.3.0...v0.3.1) (2026-10-31)


### Bug Fixes

* show the Habbo fan site disclaimer on every page ([#6](https://github.com/aaimang/wiredbench/issues/6)) ([c29708c](https://github.com/aaimang/wiredbench/commit/c29708c8e614c346a862435915dc81b360822a45))

## [0.3.0](https://github.com/aaimang/wiredbench/compare/v0.2.0...v0.3.0) (2026-10-31)


### Features

* add room editor with real furni art, avatars, walking and sitting ([#3](https://github.com/aaimang/wiredbench/issues/3)) ([8508d8b](https://github.com/aaimang/wiredbench/commit/8508d8bcdd040cca69feb028ea773cdf06867e98))
* add WIRED engine, run mode, box settings and time tracking example ([#5](https://github.com/aaimang/wiredbench/issues/5)) ([2472c67](https://github.com/aaimang/wiredbench/commit/2472c67194ba83a9a22a073c210737cdb439f723))

## [0.2.0](https://github.com/aaimang/wiredbench/compare/v0.1.0...v0.2.0) (2026-10-31)


### Features

* add foundation with login, WIRED catalogue, furnidata updates and workspace ([#1](https://github.com/aaimang/wiredbench/issues/1)) ([c6f2053](https://github.com/aaimang/wiredbench/commit/c6f20538b6fcda9ade88f0dd5fe8b93ffad31efd))
