# Changelog

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
